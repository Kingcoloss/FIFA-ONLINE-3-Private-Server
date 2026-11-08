using System.Net;
using System.Security.Cryptography.X509Certificates;
using FO3.Application.Abstractions;
using FO3.Host.Messenger;
using FO3.Host.Proxy;
using FO3.Infrastructure.State;
using FO3.Infrastructure.Time;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.Extensions.Options;
using Yarp.ReverseProxy.Configuration;
using Yarp.ReverseProxy.Transforms;

namespace FO3.Host;

/// <summary>
/// The .NET game server, phase 1 of the move (strangler): it owns https://APSEODESK172:443 and
/// the messenger, and forwards every game request it does not handle itself (all of them, for
/// now) to the Python server behind it. Requests Python answers with its generic fallback are
/// counted (GET /_fo3/fallbacks) and, with Golden:RecordDir, every exchange is recorded.
/// </summary>
public static class HostApp
{
    public static WebApplication Build(string[] args, Action<WebApplicationBuilder>? configure = null)
    {
        // appsettings.json next to the binaries, whatever folder `dotnet run` starts in
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { Args = args, ContentRootPath = AppContext.BaseDirectory });
        builder.Services.Configure<Fo3Options>(builder.Configuration.GetSection("Fo3"));
        var o = builder.Configuration.GetSection("Fo3").Get<Fo3Options>() ?? new Fo3Options();

        builder.WebHost.ConfigureKestrel(k =>
        {
            k.AddServerHeader = false;
            k.Listen(IPAddress.Parse(o.Https.Bind), o.Https.Port, listen =>
            {
                listen.Protocols = HttpProtocols.Http1; // the client's WinINet speaks HTTP/1.1
                if (o.Https.Enabled)
                    listen.UseHttps(LoadCertificate(RepoPath(o.Https.CertPem)));
            });
        });

        builder.Services.AddSingleton<IClock, SystemClock>();
        builder.Services.AddSingleton<FallbackMonitor>();
        builder.Services.AddSingleton<IGameStateStore>(sp =>
            new JsonFileStateStore(RepoPath(sp.GetRequiredService<IOptions<Fo3Options>>().Value.StatePath)));
        if (o.Messenger.Enabled)
        {
            builder.Services.AddSingleton<MessengerServer>();
            builder.Services.AddHostedService(sp => sp.GetRequiredService<MessengerServer>());
        }

        builder.Services.AddReverseProxy()
            .LoadFromMemory(
                [new RouteConfig { RouteId = "python", ClusterId = "python", Match = new RouteMatch { Path = "{**catch-all}" } }],
                [new ClusterConfig
                {
                    ClusterId = "python",
                    Destinations = new Dictionary<string, DestinationConfig> { ["python"] = new() { Address = o.Backend.Url } },
                    HttpRequest = new Yarp.ReverseProxy.Forwarder.ForwarderRequestConfig { ActivityTimeout = TimeSpan.FromMinutes(2) },
                }])
            .AddTransforms(t =>
            {
                t.AddOriginalHost(true); // Python logs the Host the client asked for
                t.AddResponseTransform(ctx =>
                {
                    if (ctx.ProxyResponse?.Headers.Contains(FallbackMonitor.Header) == true)
                    {
                        var http = ctx.HttpContext;
                        http.RequestServices.GetRequiredService<FallbackMonitor>().Record(
                            http.Request.Method, http.Request.Path.Value ?? "/", http.RequestServices.GetRequiredService<IClock>().UtcNow);
                        http.Items[FallbackMonitor.Header] = true;
                        http.Response.Headers.Remove(FallbackMonitor.Header);
                    }
                    return ValueTask.CompletedTask;
                });
            });

        configure?.Invoke(builder);
        var app = builder.Build();

        app.UseMiddleware<GoldenRecorder>();
        // the host's own endpoints: loopback only, under a prefix the client never uses
        app.MapGet("/_fo3/health", () => Results.Ok(new { ok = true })).AddEndpointFilter(LoopbackOnly);
        app.MapGet("/_fo3/fallbacks", (FallbackMonitor m) => Results.Ok(m.Snapshot())).AddEndpointFilter(LoopbackOnly);
        app.MapReverseProxy();
        return app;
    }

    private static async ValueTask<object?> LoopbackOnly(EndpointFilterInvocationContext ctx, EndpointFilterDelegate next)
    {
        var ip = ctx.HttpContext.Connection.RemoteIpAddress;
        return ip is null || IPAddress.IsLoopback(ip) ? await next(ctx) : Results.NotFound();
    }

    /// <summary>The repository (the folder with http_config.py) above the binaries, else the working folder.</summary>
    public static string RepoRoot()
    {
        for (var d = new DirectoryInfo(AppContext.BaseDirectory); d is not null; d = d.Parent)
            if (File.Exists(Path.Combine(d.FullName, "http_config.py")))
                return d.FullName;
        return Directory.GetCurrentDirectory();
    }

    /// <summary>A configured path: as given when absolute, else under the repository.</summary>
    public static string RepoPath(string path) =>
        Path.IsPathRooted(path) ? path : Path.GetFullPath(Path.Combine(RepoRoot(), path));

    /// <summary>
    /// The certificate + key PEM (one file, as Python's load_cert_chain takes it). Re-imported
    /// through PKCS#12: SChannel on Windows cannot use the ephemeral key a PEM load gives.
    /// </summary>
    public static X509Certificate2 LoadCertificate(string pem)
    {
        using var ephemeral = X509Certificate2.CreateFromPemFile(pem, pem);
        return X509CertificateLoader.LoadPkcs12(ephemeral.Export(X509ContentType.Pkcs12), null);
    }
}
