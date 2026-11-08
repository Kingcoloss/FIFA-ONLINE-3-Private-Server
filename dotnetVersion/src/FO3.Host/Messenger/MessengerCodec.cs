using System.Buffers.Binary;
using System.Text;
using System.Text.Json.Nodes;
using FO3.Infrastructure.Serialization;
using Org.BouncyCastle.Crypto.Engines;
using Org.BouncyCastle.Crypto.Modes;
using Org.BouncyCastle.Crypto.Parameters;

namespace FO3.Host.Messenger;

/// <summary>
/// The frames of fifazf.exe's MessengerConnection, as messenger.py reads and writes them:
/// <c>u16 LE body length | u16 LE type | body</c>; type 2 bodies are Blowfish-CBC (key "kueec",
/// IV 0) of the JSON text + "\n", PKCS#5 padded. JSON goes out as Python's json.dumps compact
/// text, so a frame is byte for byte the one messenger.py sends.
/// </summary>
public static class MessengerCodec
{
    public const int JsonType = 2;
    private static readonly byte[] Key = "kueec"u8.ToArray();

    private static CbcBlockCipher Cipher(bool encrypt)
    {
        var c = new CbcBlockCipher(new BlowfishEngine());
        c.Init(encrypt, new ParametersWithIV(new KeyParameter(Key), new byte[8]));
        return c;
    }

    private static byte[] Run(bool encrypt, byte[] data)
    {
        if (data.Length % 8 != 0) throw new ArgumentException($"{data.Length} bytes: not a whole number of blocks");
        var c = Cipher(encrypt);
        var output = new byte[data.Length];
        for (var i = 0; i < data.Length; i += 8)
            c.ProcessBlock(data, i, output, i);
        return output;
    }

    /// <summary>A whole frame for one message. Throws when it would not fit the u16 length.</summary>
    public static byte[] Encode(JsonNode message)
    {
        var text = Encoding.UTF8.GetBytes(PyJson.Dumps(message) + "\n");
        var pad = 8 - text.Length % 8;
        var plain = new byte[text.Length + pad];
        text.CopyTo(plain, 0);
        plain.AsSpan(text.Length).Fill((byte)pad);
        var body = Run(true, plain);
        if (body.Length > ushort.MaxValue)
            throw new InvalidOperationException($"message too long for one frame ({body.Length} bytes)");
        var frame = new byte[4 + body.Length];
        BinaryPrimitives.WriteUInt16LittleEndian(frame, (ushort)body.Length);
        BinaryPrimitives.WriteUInt16LittleEndian(frame.AsSpan(2), JsonType);
        body.CopyTo(frame, 4);
        return frame;
    }

    /// <summary>The JSON message of a type 2 body (padding dropped as messenger.py drops it).</summary>
    public static JsonNode? Decode(byte[] body)
    {
        var plain = Run(false, body);
        var n = plain.Length - plain[^1];
        return JsonNode.Parse(Encoding.UTF8.GetString(plain, 0, Math.Max(0, n)));
    }

    /// <summary>messenger.py's replies(): what the server answers one client message with.</summary>
    public static IReadOnlyList<JsonObject> Replies(JsonNode? message)
    {
        var cmd = (message as JsonObject)?["cmd"]?.GetValueKind() == System.Text.Json.JsonValueKind.String
            ? (string?)message!["cmd"]
            : null;
        return cmd switch
        {
            "auth" => [new JsonObject { ["cmd"] = "auth", ["result"] = true }],
            "ping" => [new JsonObject { ["cmd"] = "ping" }], // "pong" makes the client quit
            "signon" => [new JsonObject { ["cmd"] = "sign", ["result"] = true }],
            _ => [],
        };
    }
}
