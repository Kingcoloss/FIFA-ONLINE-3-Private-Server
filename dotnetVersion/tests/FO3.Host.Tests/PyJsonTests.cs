using System.Text.Json.Nodes;
using FO3.Infrastructure.Serialization;
using Xunit.Abstractions;

namespace FO3.Host.Tests;

/// <summary>PyJson against Python's json.dumps and repr (Golden/pyjson.json).</summary>
public sealed class PyJsonTests(ITestOutputHelper output)
{
    [Fact]
    public void Float_repr_matches_Python()
    {
        var n = 0;
        foreach (var f in Golden.Load("pyjson.json").GetProperty("floats").EnumerateArray())
        {
            Assert.Equal(f.GetProperty("repr").GetString(), PyJson.FloatRepr(f.GetProperty("value").GetDouble()));
            n++;
        }
        output.WriteLine($"{n} floats match repr()");
    }

    [Fact]
    public void Dumps_matches_Python_compact_and_default()
    {
        foreach (var d in Golden.Load("pyjson.json").GetProperty("docs").EnumerateArray())
        {
            var doc = JsonNode.Parse(d.GetProperty("doc").GetRawText());
            Assert.Equal(d.GetProperty("compact").GetString(), PyJson.Dumps(doc));
            Assert.Equal(d.GetProperty("default").GetString(), PyJson.Dumps(doc, compact: false));
        }
    }

    [Fact]
    public void Values_built_in_dotnet_come_out_as_Python_writes_them()
    {
        var o = new JsonObject { ["i"] = 3, ["l"] = 1L << 40, ["d"] = 0.5, ["whole"] = 2.0, ["s"] = "ไทย", ["b"] = false, ["n"] = null };
        Assert.Equal("{\"i\":3,\"l\":1099511627776,\"d\":0.5,\"whole\":2.0,\"s\":\"\\u0e44\\u0e17\\u0e22\",\"b\":false,\"n\":null}", PyJson.Dumps(o));
    }
}
