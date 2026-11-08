using System.IO.Compression;
using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using FO3.Host.Proxy;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.DependencyInjection;

namespace FO3.Host.Tests;

/// <summary>
/// The strangler: the host forwards the client's requests to a stand-in for the Python server
/// unchanged, counts the ones answered by its fallback, and records every exchange.
/// </summary>
public sealed class ProxyTests : IAsyncLifetime
{
    private WebApplication _backend = null!;
    private WebApplication _host = null!;
    private HttpClient _client = null!;
    private readonly string _golden = Path.Combine(Path.GetTempPath(), "fo3-golden-" + Guid.NewGuid().ToString("N"));

    public async Task InitializeAsync()
    {
        // a stand-in for http_config.py: one real endpoint, an echo, and the generic fallback
        var b = WebApplication.CreateBuilder();
        b.WebHost.UseUrls("http://127.0.0.1:0");
        _backend = b.Build();
        _backend.MapGet("/info/server/config", () => Results.Text("{\"region\": \"TH\", \"status\": \"ok\"}", "application/json"));
        _backend.MapMethods("/echo", ["POST", "PUT"], async (HttpContext ctx) =>
        {
            using var m = new MemoryStream();
            await ctx.Request.Body.CopyToAsync(m);
            return Results.Json(new
            {
                method = ctx.Request.Method,
                host = ctx.Request.Host.Value,
                query = ctx.Request.QueryString.Value,
                encoding = ctx.Request.Headers.ContentEncoding.ToString(),
                body = Convert.ToBase64String(m.ToArray()),
            });
        });
        _backend.MapFallback((HttpContext ctx) =>
        {
            ctx.Response.Headers[FallbackMonitor.Header] = "1";
            return Results.Text(ctx.Request.Method == "POST" ? "{\"result\": true}" : "{}", "application/json");
        });
        await _backend.StartAsync();
        var url = _backend.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.First();

        _host = HostApp.Build(
            [$"--Fo3:Backend:Url={url}/", "--Fo3:Messenger:Enabled=false", $"--Fo3:Golden:RecordDir={_golden}"],
            builder => builder.WebHost.UseTestServer());
        await _host.StartAsync();
        _client = _host.GetTestClient();
    }

    public async Task DisposeAsync()
    {
        await _host.StopAsync();
        await _backend.StopAsync();
        if (Directory.Exists(_golden)) Directory.Delete(_golden, true);
    }

    [Fact]
    public async Task A_handled_request_passes_through_unchanged()
    {
        var r = await _client.GetAsync("/info/server/config");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        Assert.Equal("{\"region\": \"TH\", \"status\": \"ok\"}", await r.Content.ReadAsStringAsync());
        Assert.False(r.Headers.Contains(FallbackMonitor.Header));
    }

    [Fact]
    public async Task A_gzipped_body_query_and_host_reach_the_backend_as_sent()
    {
        var plain = Encoding.UTF8.GetBytes("{\"squad\": [1, 2, 3], \"name\": \"ทดสอบ\"}");
        using var gz = new MemoryStream();
        using (var z = new GZipStream(gz, CompressionLevel.Fastest, leaveOpen: true)) z.Write(plain);
        var req = new HttpRequestMessage(HttpMethod.Put, "/echo?a=1&b=x") { Content = new ByteArrayContent(gz.ToArray()) };
        req.Content.Headers.ContentEncoding.Add("gzip");
        req.Headers.Host = "APSEODESK172";
        var r = await _client.SendAsync(req);
        var echo = await r.Content.ReadFromJsonAsync<JsonElement>();
        Assert.Equal("PUT", echo.GetProperty("method").GetString());
        Assert.Equal("APSEODESK172", echo.GetProperty("host").GetString());
        Assert.Equal("?a=1&b=x", echo.GetProperty("query").GetString());
        Assert.Equal("gzip", echo.GetProperty("encoding").GetString());
        Assert.Equal(gz.ToArray(), Convert.FromBase64String(echo.GetProperty("body").GetString()!));
    }

    [Fact]
    public async Task Fallback_answers_are_counted_and_the_marker_stays_inside()
    {
        for (var i = 0; i < 2; i++)
        {
            var r = await _client.GetAsync("/worldcup/me/team");
            Assert.Equal("{}", await r.Content.ReadAsStringAsync());
            Assert.False(r.Headers.Contains(FallbackMonitor.Header));
        }
        await _client.PostAsync("/telemetry/x", new StringContent("{}"));
        var hits = await _client.GetFromJsonAsync<JsonElement>("/_fo3/fallbacks");
        var byPath = hits.EnumerateArray().ToDictionary(h => h.GetProperty("method").GetString() + " " + h.GetProperty("path").GetString(),
            h => h.GetProperty("count").GetInt64());
        Assert.Equal(2, byPath["GET /worldcup/me/team"]);
        Assert.Equal(1, byPath["POST /telemetry/x"]);
        Assert.False(byPath.ContainsKey("GET /info/server/config"));
    }

    [Fact]
    public async Task Every_exchange_is_recorded_for_the_golden_tests()
    {
        await _client.GetAsync("/info/server/config");
        await _client.GetAsync("/worldcup/me/team");
        var lines = Directory.GetFiles(_golden, "golden-*.jsonl").SelectMany(File.ReadAllLines)
            .Select(l => JsonNode.Parse(l)!.AsObject()).ToList();
        var config = lines.Last(l => (string?)l["path"] == "/info/server/config");
        Assert.Equal("GET", (string?)config["method"]);
        Assert.Equal(200, (int?)config["status"]);
        Assert.Equal("{\"region\": \"TH\", \"status\": \"ok\"}",
            Encoding.UTF8.GetString(Convert.FromBase64String((string)config["response"]!["base64"]!)));
        Assert.False((bool?)config["fallback"]);
        Assert.True((bool?)lines.Last(l => (string?)l["path"] == "/worldcup/me/team")["fallback"]);
    }
}
