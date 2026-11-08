using System.Numerics;
using System.Text.Json;
using FO3.Domain.Randomness;
using Xunit.Abstractions;

namespace FO3.Domain.Tests;

/// <summary>PyRandom against draws made by CPython (Golden/pyrandom.json, tools/golden/gen_pyrandom_golden.py).</summary>
public sealed class PyRandomGoldenTests(ITestOutputHelper output)
{
    private static JsonElement Golden(string name) =>
        JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Golden", name))).RootElement;

    private static bool SameDouble(double a, double b) => BitConverter.DoubleToInt64Bits(a) == BitConverter.DoubleToInt64Bits(b);

    private static long[] Ints(JsonElement e) => e.EnumerateArray().Select(x => x.GetInt64()).ToArray();

    [Fact]
    public void Every_method_matches_CPython_for_int_and_str_seeds()
    {
        var checkedValues = 0;
        foreach (var c in Golden("pyrandom.json").GetProperty("cases").EnumerateArray())
        {
            var seed = c.GetProperty("seed").GetString()!;
            var r = c.GetProperty("kind").GetString() == "int" ? new PyRandom(BigInteger.Parse(seed)) : new PyRandom(seed);
            var ops = c.GetProperty("ops").EnumerateArray().ToArray();
            var outs = c.GetProperty("out").EnumerateArray().ToArray();
            for (var i = 0; i < ops.Length; i++)
            {
                var op = ops[i].EnumerateArray().ToArray();
                var name = op[0].GetString();
                var want = outs[i];
                var where = $"seed {seed!} op {i} {ops[i]}";
                switch (name)
                {
                    case "random":
                        Assert.True(SameDouble(want.GetDouble(), r.Random()), where);
                        break;
                    case "uniform":
                        Assert.True(SameDouble(want.GetDouble(), r.Uniform(op[1].GetDouble(), op[2].GetDouble())), where);
                        break;
                    case "randint":
                        Assert.Equal(want.GetInt64(), r.RandInt(op[1].GetInt64(), op[2].GetInt64()));
                        break;
                    case "randrange":
                        var got = op.Length switch
                        {
                            2 => r.RandRange(op[1].GetInt64()),
                            3 => r.RandRange(op[1].GetInt64(), op[2].GetInt64()),
                            _ => r.RandRange(op[1].GetInt64(), op[2].GetInt64(), op[3].GetInt64()),
                        };
                        Assert.Equal(want.GetInt64(), got);
                        break;
                    case "choice":
                        Assert.Equal(want.GetInt64(), r.Choice(Enumerable.Range(0, op[1].GetInt32()).ToArray()));
                        break;
                    case "shuffle":
                        var x = Enumerable.Range(0, op[1].GetInt32()).Select(v => (long)v).ToList();
                        r.Shuffle(x);
                        Assert.Equal(Ints(want), x);
                        break;
                    case "sample":
                        var pop = Enumerable.Range(0, op[1].GetInt32()).Select(v => (long)v).ToArray();
                        Assert.Equal(Ints(want), r.Sample(pop, op[2].GetInt32()));
                        break;
                    case "choices":
                        var k = op[2].GetInt32();
                        if (op[1].ValueKind == JsonValueKind.Null)
                            Assert.Equal(Ints(want), r.Choices(Enumerable.Range(0, 5).Select(v => (long)v).ToArray(), k));
                        else
                        {
                            var w = op[1].EnumerateArray().Select(v => v.GetDouble()).ToArray();
                            Assert.Equal(Ints(want), r.Choices(Enumerable.Range(0, w.Length).Select(v => (long)v).ToArray(), w, k));
                        }
                        break;
                    default:
                        throw new InvalidOperationException(name);
                }
                checkedValues++;
            }
        }
        output.WriteLine($"{checkedValues} draws match CPython");
    }

    [Fact]
    public void A_long_run_matches_across_state_refills()
    {
        var run = Golden("pyrandom.json").GetProperty("longrun");
        var r = new PyRandom(30);
        var n = 0;
        foreach (var want in run.GetProperty("random").EnumerateArray())
        {
            Assert.True(SameDouble(want.GetDouble(), r.Random()), $"draw {n}");
            n++;
        }
        output.WriteLine($"{n} random() draws match CPython");
    }
}
