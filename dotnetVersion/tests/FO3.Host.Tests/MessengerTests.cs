using System.Buffers.Binary;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json.Nodes;
using FO3.Host.Messenger;
using Microsoft.Extensions.Logging.Abstractions;
using Microsoft.Extensions.Options;

namespace FO3.Host.Tests;

/// <summary>The .NET messenger against messenger.py (Golden/messenger.json) and over a real socket.</summary>
public sealed class MessengerTests
{
    private static readonly System.Text.Json.JsonElement G = Golden.Load("messenger.json");

    [Fact]
    public void Frames_are_byte_for_byte_messenger_py()
    {
        foreach (var f in G.GetProperty("frames").EnumerateArray())
        {
            var message = JsonNode.Parse(f.GetProperty("message").GetRawText())!;
            var frame = MessengerCodec.Encode(message);
            Assert.Equal(f.GetProperty("frame").GetString(), Convert.ToHexStringLower(frame));
            Assert.True(JsonNode.DeepEquals(message, MessengerCodec.Decode(frame[4..])));
        }
    }

    [Fact]
    public void The_real_clients_first_frame_decodes()
    {
        var c = G.GetProperty("client_first");
        var got = MessengerCodec.Decode(Convert.FromHexString(c.GetProperty("body").GetString()!));
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(c.GetProperty("message").GetRawText()), got));
    }

    [Fact]
    public void Replies_match_messenger_py()
    {
        foreach (var r in G.GetProperty("replies").EnumerateArray())
        {
            var want = JsonNode.Parse(r.GetProperty("replies").GetRawText())!.AsArray();
            var got = MessengerCodec.Replies(JsonNode.Parse(r.GetProperty("message").GetRawText()));
            Assert.Equal(want.Count, got.Count);
            for (var i = 0; i < got.Count; i++) Assert.True(JsonNode.DeepEquals(want[i], got[i]));
        }
    }

    private static async Task<JsonNode?> ReadFrame(NetworkStream s)
    {
        var head = new byte[4];
        await s.ReadExactlyAsync(head);
        Assert.Equal(MessengerCodec.JsonType, BinaryPrimitives.ReadUInt16LittleEndian(head.AsSpan(2)));
        var body = new byte[BinaryPrimitives.ReadUInt16LittleEndian(head)];
        await s.ReadExactlyAsync(body);
        return MessengerCodec.Decode(body);
    }

    [Fact]
    public async Task A_client_signs_on_and_gets_pushes()
    {
        var options = Options.Create(new Fo3Options { Messenger = { Bind = "127.0.0.1", Port = 0, PushPort = 0 } });
        var server = new MessengerServer(options, NullLogger<MessengerServer>.Instance);
        using var stop = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        await server.StartAsync(stop.Token);
        await server.Listening;
        try
        {
            using var tcp = new TcpClient();
            await tcp.ConnectAsync(IPAddress.Loopback, server.Port, stop.Token);
            var s = tcp.GetStream();

            // the real client's first frame, then a ping split over two writes
            var first = Convert.FromHexString(G.GetProperty("client_first").GetProperty("body").GetString()!);
            var frame = new byte[4 + first.Length];
            BinaryPrimitives.WriteUInt16LittleEndian(frame, (ushort)first.Length);
            BinaryPrimitives.WriteUInt16LittleEndian(frame.AsSpan(2), 2);
            first.CopyTo(frame, 4);
            await s.WriteAsync(frame, stop.Token);
            Assert.True(JsonNode.DeepEquals(new JsonObject { ["cmd"] = "auth", ["result"] = true }, await ReadFrame(s)));

            var ping = MessengerCodec.Encode(new JsonObject { ["cmd"] = "ping" });
            await s.WriteAsync(ping.AsMemory(0, 3), stop.Token);
            await Task.Delay(50, stop.Token);
            await s.WriteAsync(ping.AsMemory(3), stop.Token);
            Assert.True(JsonNode.DeepEquals(new JsonObject { ["cmd"] = "ping" }, await ReadFrame(s)));

            // the game server's push (http_config.py sends one UDP datagram)
            while (server.ClientCount == 0) await Task.Delay(10, stop.Token);
            using var udp = new UdpClient();
            var push = "{\"cmd\": \"push\", \"uri\": \"/ladder/room\", \"body\": {\"roomid\": 7, \"name\": \"ไทย\"}}";
            await udp.SendAsync(Encoding.UTF8.GetBytes(push), new IPEndPoint(IPAddress.Loopback, server.PushPort), stop.Token);
            Assert.True(JsonNode.DeepEquals(JsonNode.Parse(push), await ReadFrame(s)));
        }
        finally
        {
            await server.StopAsync(CancellationToken.None);
        }
    }
}
