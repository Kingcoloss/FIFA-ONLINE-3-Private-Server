using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using FO3.Application.Abstractions;
using Microsoft.Extensions.Options;

namespace FO3.Host.Proxy;

/// <summary>
/// Records every request and the answer it got as one JSON line in Golden:RecordDir
/// (golden-YYYYMMDD.jsonl): the material of the golden contract tests, replayed later against the
/// .NET endpoints and diffed. Off when RecordDir is empty.
/// </summary>
public sealed class GoldenRecorder(RequestDelegate next, IOptions<Fo3Options> options, IClock clock, ILogger<GoldenRecorder> log)
{
    private static readonly SemaphoreSlim FileGate = new(1, 1);

    public async Task InvokeAsync(HttpContext ctx)
    {
        var o = options.Value.Golden;
        if (string.IsNullOrWhiteSpace(o.RecordDir) || ctx.Request.Path.StartsWithSegments("/_fo3"))
        {
            await next(ctx);
            return;
        }

        ctx.Request.EnableBuffering();
        var request = await ReadAll(ctx.Request.Body);
        ctx.Request.Body.Position = 0;

        var original = ctx.Response.Body;
        await using var copy = new MemoryStream();
        var tee = new TeeStream(original, copy, o.MaxBodyBytes);
        ctx.Response.Body = tee;
        var at = clock.UtcNow;
        try
        {
            await next(ctx);
        }
        finally
        {
            ctx.Response.Body = original;
        }

        var line = new JsonObject
        {
            ["at"] = at.ToUnixTimeMilliseconds(),
            ["method"] = ctx.Request.Method,
            ["path"] = ctx.Request.Path.Value,
            ["query"] = ctx.Request.QueryString.HasValue ? ctx.Request.QueryString.Value![1..] : "",
            ["requestType"] = ctx.Request.ContentType,
            ["requestEncoding"] = ctx.Request.Headers.ContentEncoding.ToString(),
            ["request"] = Body(request, request.Length, o.MaxBodyBytes),
            ["status"] = ctx.Response.StatusCode,
            ["responseType"] = ctx.Response.ContentType,
            ["response"] = Body(copy.ToArray(), tee.Length, o.MaxBodyBytes),
            ["fallback"] = ctx.Items.ContainsKey(FallbackMonitor.Header),
        };
        try
        {
            Directory.CreateDirectory(o.RecordDir);
            var file = Path.Combine(o.RecordDir, $"golden-{at:yyyyMMdd}.jsonl");
            await FileGate.WaitAsync();
            try { await File.AppendAllTextAsync(file, line.ToJsonString() + "\n", Encoding.UTF8); }
            finally { FileGate.Release(); }
        }
        catch (IOException e)
        {
            log.LogWarning("golden record not written: {Error}", e.Message);
        }
    }

    private static async Task<byte[]> ReadAll(Stream s)
    {
        using var m = new MemoryStream();
        await s.CopyToAsync(m);
        return m.ToArray();
    }

    /// <summary>{length, base64} of a body up to max bytes; a longer one: its length (and hash when whole).</summary>
    private static JsonObject Body(byte[] kept, long length, int max)
    {
        var o = new JsonObject { ["length"] = length };
        if (length <= max && kept.Length == length)
            o["base64"] = Convert.ToBase64String(kept);
        else if (kept.Length == length)
            o["sha256"] = Convert.ToHexStringLower(SHA256.HashData(kept));
        return o;
    }

    /// <summary>Writes through to the client and keeps a copy of the first max bytes.</summary>
    private sealed class TeeStream(Stream inner, MemoryStream copy, int max) : Stream
    {
        private long _length;
        public override bool CanRead => false;
        public override bool CanSeek => false;
        public override bool CanWrite => true;
        public override long Length => _length;
        public override long Position { get => _length; set => throw new NotSupportedException(); }
        public override void Flush() => inner.Flush();
        public override Task FlushAsync(CancellationToken ct) => inner.FlushAsync(ct);
        public override int Read(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();

        private void Keep(ReadOnlySpan<byte> data)
        {
            _length += data.Length;
            var room = max + 1 - (int)copy.Length; // one byte over max marks "longer"
            if (room > 0) copy.Write(data[..Math.Min(room, data.Length)]);
        }

        public override void Write(byte[] buffer, int offset, int count)
        {
            Keep(buffer.AsSpan(offset, count));
            inner.Write(buffer, offset, count);
        }

        public override async ValueTask WriteAsync(ReadOnlyMemory<byte> buffer, CancellationToken ct = default)
        {
            Keep(buffer.Span);
            await inner.WriteAsync(buffer, ct);
        }

        public override Task WriteAsync(byte[] buffer, int offset, int count, CancellationToken ct) =>
            WriteAsync(buffer.AsMemory(offset, count), ct).AsTask();
    }
}
