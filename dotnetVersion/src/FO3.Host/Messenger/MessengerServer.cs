using System.Buffers.Binary;
using System.Collections.Concurrent;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Options;

namespace FO3.Host.Messenger;

/// <summary>
/// messenger.py in .NET: the TCP server fifazf.exe's MessengerConnection talks to (auth, ping,
/// signon), and the UDP push port on 127.0.0.1 where the game server drops {"cmd": "push", ...}
/// datagrams that go out to every connected client.
/// </summary>
public sealed class MessengerServer(IOptions<Fo3Options> options, ILogger<MessengerServer> log) : BackgroundService
{
    private readonly ConcurrentDictionary<Socket, byte> _clients = new();
    private readonly SemaphoreSlim _send = new(1, 1);
    private TcpListener? _tcp;
    private UdpClient? _udp;

    public int Port => ((IPEndPoint?)_tcp?.LocalEndpoint)?.Port ?? 0;
    public int PushPort => ((IPEndPoint?)_udp?.Client.LocalEndPoint)?.Port ?? 0;
    public int ClientCount => _clients.Count;
    private readonly TaskCompletionSource _listening = new(TaskCreationOptions.RunContinuationsAsynchronously);

    /// <summary>Completes once both sockets are bound (tests read the ports then).</summary>
    public Task Listening => _listening.Task;

    protected override async Task ExecuteAsync(CancellationToken stop)
    {
        var o = options.Value.Messenger;
        _tcp = new TcpListener(IPAddress.Parse(o.Bind), o.Port);
        _tcp.Server.ExclusiveAddressUse = OperatingSystem.IsWindows(); // no second server on the same port
        _tcp.Start();
        _udp = new UdpClient(new IPEndPoint(IPAddress.Loopback, o.PushPort ?? (o.Port == 0 ? 0 : o.Port + 1)));
        log.LogInformation("messenger on {Bind}:{Port}, pushes from 127.0.0.1:{Push}", o.Bind, Port, PushPort);
        _listening.TrySetResult();
        var push = PushLoop(stop);
        try
        {
            while (!stop.IsCancellationRequested)
            {
                var s = await _tcp.AcceptSocketAsync(stop);
                _ = Serve(s, stop);
            }
        }
        catch (OperationCanceledException) { }
        finally
        {
            _tcp.Stop();
            _udp.Dispose();
            foreach (var c in _clients.Keys) c.Dispose();
        }
        await push.ContinueWith(_ => { });
    }

    private async Task Send(Socket s, byte[] frame, CancellationToken ct)
    {
        await _send.WaitAsync(ct);
        try { await s.SendAsync(frame, SocketFlags.None, ct); }
        finally { _send.Release(); }
    }

    private async Task Serve(Socket s, CancellationToken stop)
    {
        var who = s.RemoteEndPoint;
        log.LogInformation("connect {Client}", who);
        _clients[s] = 0;
        var buf = new MemoryStream();
        var chunk = new byte[65536];
        try
        {
            while (true)
            {
                var n = await s.ReceiveAsync(chunk, SocketFlags.None, stop);
                if (n == 0) break;
                buf.Write(chunk, 0, n);
                while (true)
                {
                    var data = buf.GetBuffer().AsSpan(0, (int)buf.Length);
                    if (data.Length < 4) break;
                    var len = BinaryPrimitives.ReadUInt16LittleEndian(data);
                    var type = BinaryPrimitives.ReadUInt16LittleEndian(data[2..]);
                    if (data.Length < 4 + len) break;
                    var body = data.Slice(4, len).ToArray();
                    var rest = data[(4 + len)..].ToArray();
                    buf.SetLength(0);
                    buf.Write(rest);

                    JsonNode? msg;
                    try
                    {
                        msg = type == MessengerCodec.JsonType
                            ? MessengerCodec.Decode(body)
                            : new JsonObject { ["raw"] = Convert.ToHexStringLower(body), ["type"] = type };
                    }
                    catch (Exception e)
                    {
                        msg = new JsonObject { ["undecodable"] = Convert.ToHexStringLower(body), ["error"] = e.Message };
                    }
                    if ((string?)(msg as JsonObject)?["cmd"] != "ping")
                        log.LogInformation("<- {Message}", msg?.ToJsonString());
                    foreach (var reply in MessengerCodec.Replies(msg))
                    {
                        await Send(s, MessengerCodec.Encode(reply), stop);
                        if ((string?)reply["cmd"] != "ping")
                            log.LogInformation("-> {Reply}", reply.ToJsonString());
                    }
                }
            }
        }
        catch (Exception e) when (e is OperationCanceledException or SocketException or ObjectDisposedException) { }
        finally
        {
            _clients.TryRemove(s, out _);
            s.Dispose();
            log.LogInformation("closed {Client}", who);
        }
    }

    private async Task PushLoop(CancellationToken stop)
    {
        while (!stop.IsCancellationRequested)
        {
            UdpReceiveResult got;
            try { got = await _udp!.ReceiveAsync(stop); }
            catch (Exception e) when (e is OperationCanceledException or ObjectDisposedException) { return; }
            catch (SocketException) { continue; } // Windows: ICMP port unreachable from an earlier send
            byte[] frame;
            try
            {
                frame = MessengerCodec.Encode(JsonNode.Parse(got.Buffer) ?? throw new FormatException("null"));
            }
            catch (Exception e) // bad JSON, too long for the u16 frame...: drop it, keep the loop
            {
                log.LogWarning("push dropped: {Error}", e.Message);
                continue;
            }
            foreach (var c in _clients.Keys)
            {
                try { await Send(c, frame, stop); }
                catch (Exception e) when (e is SocketException or ObjectDisposedException) { _clients.TryRemove(c, out _); }
            }
            var head = Encoding.UTF8.GetString(got.Buffer, 0, Math.Min(120, got.Buffer.Length));
            log.LogInformation("push -> {Count} client(s): {Head}", _clients.Count, head);
        }
    }
}
