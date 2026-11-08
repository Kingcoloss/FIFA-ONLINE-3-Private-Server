using System.Globalization;
using System.Text.Json;
using FO3.Domain.Randomness;

namespace FO3.Domain.Tests.Spikes;

/// <summary>
/// Feasibility spike, not the production port: http_config.py's virtual-manager crowd (vm_make,
/// vm_base, vm_group, vm_extra, vm_newcomers), their Rank games (vm_play), the small seeded picks
/// (vm_skill, vm_personality, vm_style, vm_region), club points (club_vm_points), the AI clubs
/// (ai_clubs) and market prices (market_factor), line for line on <see cref="PyRandom"/>.
/// The constants come from the golden file, as Python exported them.
/// </summary>
public sealed class VirtualManagerSpike
{
    public sealed class Vm
    {
        public required string Id, Name;
        public required int Level, TeamId, Grade;
        public required int[] Elo, Wins, Forfeits, Losses;
        public List<int>? Hours;
    }

    public sealed record Club(string Id, string Name, long Created, int Color, bool AllowJoin, int Limit, List<(string Id, long Joined, int Grade)> Members);

    private sealed record Tier(double Share, int[] Grades, int[] Levels, int[] Ratings);

    private readonly JsonElement _in;
    private readonly Tier[] _tiers;
    private readonly int[][] _thirds;
    private readonly int _ladderCount;

    public VirtualManagerSpike(JsonElement inputs)
    {
        _in = inputs;
        _tiers = inputs.GetProperty("VM_TIERS").EnumerateArray().Select(t =>
        {
            var a = t.EnumerateArray().ToArray();
            return new Tier(a[0].GetDouble(), IntArr(a[1]), IntArr(a[2]), IntArr(a[3]));
        }).ToArray();
        _thirds = inputs.GetProperty("THIRDS").EnumerateArray().Select(IntArr).ToArray();
        _ladderCount = I("LADDER_COUNT");
    }

    private static string S(FormattableString f) => f.ToString(CultureInfo.InvariantCulture);
    private static int[] IntArr(JsonElement e) => e.EnumerateArray().Select(x => x.GetInt32()).ToArray();
    private static string[] StrArr(JsonElement e) => e.EnumerateArray().Select(x => x.GetString()!).ToArray();
    private int I(string name) => _in.GetProperty(name).GetInt32();
    private long L(string name) => _in.GetProperty(name).GetInt64();
    private int[] Ints(string name) => IntArr(_in.GetProperty(name));
    private string[] Strs(string name) => StrArr(_in.GetProperty(name));

    private static List<string> Product(string[] words, string[] tags, Func<string, bool>? keep = null) =>
        words.SelectMany(w => tags.Select(t => w + t)).Where(n => keep is null || keep(n)).ToList();

    public Vm Make(PyRandom rnd, int n, string name, int tier, bool played = true)
    {
        var t = _tiers[tier];
        var count = _ladderCount;
        var b = rnd.RandInt(t.Ratings[0], t.Ratings[1]);
        var elo = new int[count];
        for (var i = 0; i < count; i++) elo[i] = Math.Max(1000, b + rnd.RandInt(-40, 40));
        var games = new int[count];
        for (var i = 0; i < count; i++) games[i] = played ? rnd.RandInt(10, 60) * (tier + 1) : 0;
        var wins = new int[count];
        for (var i = 0; i < count; i++) wins[i] = (int)Math.Round(games[i] * Math.Min(0.8, 0.35 + (elo[i] - 1000) / 2000.0));
        var forfeits = new int[count];
        for (var i = 0; i < count; i++) forfeits[i] = rnd.RandInt(0, games[i] / 25);
        var level = rnd.RandInt(t.Levels[0], t.Levels[1]);
        var team = rnd.Choice(_thirds[tier].Length > 0 ? _thirds[tier] : _thirds[0]);
        var grade = rnd.RandInt(t.Grades[0], t.Grades[1]);
        return new Vm
        {
            Id = S($"vm{n:D4}"), Name = name, Level = level, TeamId = team, Grade = grade, Elo = elo, Wins = wins,
            Forfeits = forfeits, Losses = games.Select((g, i) => g - wins[i] - forfeits[i]).ToArray(),
        };
    }

    private List<Vm> Crowd(PyRandom rnd, int n, int firstId, List<string> pool)
    {
        var names = rnd.Sample(pool, n);
        var result = new List<Vm>();
        for (var tier = 0; tier < _tiers.Length; tier++)
        {
            var size = tier < 2 ? (int)Math.Round(_tiers[tier].Share * n) : n - result.Count;
            for (var j = 0; j < size; j++)
                result.Add(Make(rnd, firstId + result.Count, names[result.Count], tier));
        }
        return result;
    }

    public List<Vm> Base() =>
        Crowd(new PyRandom(I("VM_SEED")), I("VM_COUNT"), 0, Product(Strs("VM_WORDS"), Strs("VM_TAGS")));

    public List<Vm> Group(string seed, int n, int firstId, List<string> pool) =>
        Crowd(new PyRandom(S($"{I("VM_SEED")}/{seed}")), n, firstId, pool);

    public List<Vm> Extra()
    {
        var masked = Strs("VM_NAMES3_MASKED").ToHashSet(StringComparer.Ordinal);
        return Group("extra", I("VM_EXTRA"), I("VM_EXTRA_ID"), Product(Strs("VM_WORDS2"), Strs("VM_TAGS2")))
            .Concat(Group("extra2", I("VM_EXTRA2"), I("VM_EXTRA2_ID"), Product(Strs("VM_WORDS3"), Strs("VM_TAGS2"), n => !masked.Contains(n))))
            .ToList();
    }

    public List<(int Day, int Hour, Vm Vm)> Newcomers(int day)
    {
        var taken = Base().Select(m => m.Name).ToHashSet(StringComparer.Ordinal);
        var free = Product(Strs("VM_WORDS"), Strs("VM_TAGS"), n => !taken.Contains(n)).Order(StringComparer.Ordinal).ToList();
        var joinTier = _in.GetProperty("VM_JOIN_TIER").EnumerateArray().Select(x => x.GetDouble()).ToArray();
        var tiers = Enumerable.Range(0, _tiers.Length).ToArray();
        var result = new List<(int, int, Vm)>();
        for (var d = 1; d <= day; d++)
        {
            var rnd = new PyRandom(S($"vmjoin/{d}"));
            var count = rnd.Choice(Ints("VM_JOIN"));
            for (var j = 0; j < count; j++)
            {
                if (I("VM_COUNT") + I("VM_EXTRA") + I("VM_EXTRA2") + result.Count >= I("VM_MAX"))
                    return result;
                var tier = rnd.Choices(tiers, joinTier)[0];
                var at = (int)rnd.RandRange(free.Count);
                var name = free[at];
                free.RemoveAt(at);
                var hour = rnd.Choice(Ints("VM_HOURS"));
                result.Add((d, hour, Make(rnd, I("VM_COUNT") + result.Count, name, tier, played: false)));
            }
        }
        return result;
    }

    public static int Skill(string vid) => new PyRandom(S($"{vid}/skill")).RandInt(-60, 60);

    public void Play(Vm vm, int sid, int d, int first, (int Day, int Hour)? joined = null, int? hour = null)
    {
        var rnd = new PyRandom(S($"{vm.Id}/{sid}/{d}"));
        var skill = Skill(vm.Id);
        int? jd = joined?.Day;
        var jh = joined?.Hour ?? 0;
        var gamesOf = Ints("VM_GAMES");
        var hours = Ints("VM_HOURS");
        int start = I("LADDER_START"), k = I("LADDER_K");
        for (var i = 0; i < _ladderCount; i++)
        {
            var games = rnd.Choice(gamesOf);
            for (var g = 0; g < games; g++)
            {
                var at = rnd.Choice(hours);
                var opp = vm.Elo[i] + rnd.RandInt(-80, 80);
                var won = rnd.Random() < 1 / (1 + Math.Pow(10, (opp - vm.Elo[i] - skill) / 400.0));
                if (first + d - 1 == jd && at < jh)
                    continue;
                if (hour is not null && (i == 0 || i == 3))
                    (vm.Hours ??= []).Add(at);
                if (hour is null || at <= hour)
                {
                    var expect = 1 / (1 + Math.Pow(10, (opp - vm.Elo[i]) / 400.0));
                    vm.Elo[i] = Math.Max(start, (int)Math.Round(vm.Elo[i] + k * ((won ? 1 : 0) - expect)));
                    if (won) vm.Wins[i]++;
                    else vm.Losses[i]++;
                }
            }
        }
    }

    public string Personality(string vid) => new PyRandom(vid).Choice(Strs("VM_PERSONALITIES"));
    public string Style(string vid) => new PyRandom(S($"{vid}/style")).Choice(Strs("VM_STYLES"));
    public string Region(string vid) => new PyRandom("region" + vid).Choice(Strs("KOTH_LEAVES"));

    private static readonly int[] ClubDayPicks = [0, 1, 2, 3, 4, 6];

    public static int ClubVmDay(string vid, int day, double keen)
    {
        var r = new PyRandom(S($"clubpts:{vid}:{day}"));
        var first = r.Random() < 0.8 ? 10 : 0;
        return first + 2 * (int)Math.Round(keen * r.Choice(ClubDayPicks));
    }

    public static int ClubVmPoints(string vid, int d0, int d1)
    {
        var keen = new PyRandom("clubkeen" + vid).Uniform(0.5, 1.5);
        var exact = Math.Max(d0, d1 - 7);
        var sum = 0;
        for (var d = exact; d <= d1; d++) sum += ClubVmDay(vid, d, keen);
        return Math.Max(0, exact - d0) * (int)Math.Round(8 + 6 * keen) + sum;
    }

    public List<Club> AiClubs(IEnumerable<Vm> crowd)
    {
        var names = Strs("VM_WORDS2").SelectMany(w => Strs("CLUB_SUFFIX").Select(s => $"{w} {s}")).ToList();
        new PyRandom("clubnames").Shuffle(names);
        int count = I("CLUB_AI"), limit = I("CLUB_LIMIT"), expand = I("CLUB_EXPAND");
        long epoch = L("VM_EPOCH");
        var weights = Enumerable.Range(0, count).Select(k => 1.0 / (k + 10)).ToArray();
        var colors = Ints("CLUB_COLORS");
        var clubs = new List<Club>();
        for (var k = 0; k < count; k++)
        {
            var r = new PyRandom(S($"club{k}"));
            var created = epoch - r.RandInt(20L, 700L) * 86400;
            var color = r.Choice(colors);
            var allowJoin = r.Random() < 0.85;
            clubs.Add(new Club(S($"club{k + 1:D4}"), names[k], created, color, allowJoin, limit + expand * (k < 8 ? 1 : 0), []));
        }
        var share = _in.GetProperty("CLUB_IN").GetDouble();
        var index = Enumerable.Range(0, count).ToArray();
        foreach (var m in crowd.OrderBy(m => -m.Level).ThenBy(m => m.Id, StringComparer.Ordinal))
        {
            var r = new PyRandom("clubof" + m.Id);
            if (r.Random() < share)
            {
                var c = clubs[r.Choices(index, weights)[0]];
                if (c.Members.Count < c.Limit - 2)
                    c.Members.Add((m.Id, c.Created + r.RandInt(0L, Math.Max(0L, (epoch - c.Created) / 86400)) * 86400, 0));
            }
        }
        foreach (var c in clubs)
            for (var i = 0; i < c.Members.Count; i++)
                c.Members[i] = c.Members[i] with { Grade = i == 0 ? 10 : i == 1 ? 8 : i < 4 ? 6 : 1 };
        return clubs;
    }

    public static double MarketFactor(long spid, int grade, int day)
    {
        var r = new PyRandom(S($"price/{spid}/{grade}"));
        double p1 = r.Uniform(9, 23), p2 = r.Uniform(3, 7), a = r.Uniform(0, 2 * Math.PI), b = r.Uniform(0, 2 * Math.PI);
        var noise = new PyRandom(S($"price/{spid}/{grade}/{day}")).Uniform(-0.003, 0.003);
        return 0.975 + 0.012 * Math.Sin(2 * Math.PI * day / p1 + a) + 0.006 * Math.Sin(2 * Math.PI * day / p2 + b) + noise;
    }
}
