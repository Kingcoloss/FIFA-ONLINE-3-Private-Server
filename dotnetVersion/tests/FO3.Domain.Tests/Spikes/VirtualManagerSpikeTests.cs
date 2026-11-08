using System.Text.Json;
using Xunit.Abstractions;
using static FO3.Domain.Tests.Spikes.VirtualManagerSpike;

namespace FO3.Domain.Tests.Spikes;

/// <summary>
/// The ported crowd against http_config.py's own output (Golden/vm_spike.json): every manager,
/// every Rank game, every AI club member must come out the same.
/// </summary>
public sealed class VirtualManagerSpikeTests(ITestOutputHelper output)
{
    private static readonly JsonElement Golden =
        JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Golden", "vm_spike.json"))).RootElement;

    private readonly VirtualManagerSpike _spike = new(Golden.GetProperty("inputs"));

    private static int[] Ints(JsonElement e) => e.EnumerateArray().Select(x => x.GetInt32()).ToArray();

    private static void AssertVm(JsonElement want, Vm got)
    {
        var id = want.GetProperty("_id").GetString();
        Assert.Equal(id, got.Id);
        Assert.Equal(want.GetProperty("name").GetString(), got.Name);
        Assert.True(want.GetProperty("level").GetInt32() == got.Level, $"{id} level");
        Assert.True(want.GetProperty("teamid").GetInt32() == got.TeamId, $"{id} teamid");
        Assert.True(want.GetProperty("grade").GetInt32() == got.Grade, $"{id} grade");
        Assert.Equal(Ints(want.GetProperty("elo")), got.Elo);
        Assert.Equal(Ints(want.GetProperty("wins")), got.Wins);
        Assert.Equal(Ints(want.GetProperty("forfeits")), got.Forfeits);
        Assert.Equal(Ints(want.GetProperty("losses")), got.Losses);
        if (want.TryGetProperty("hours", out var hours))
            Assert.Equal(Ints(hours), got.Hours);
        else
            Assert.Null(got.Hours);
    }

    private static void AssertCrowd(JsonElement want, List<Vm> got)
    {
        Assert.Equal(want.GetArrayLength(), got.Count);
        var i = 0;
        foreach (var w in want.EnumerateArray()) AssertVm(w, got[i++]);
    }

    [Fact]
    public void The_whole_crowd_matches_Python()
    {
        AssertCrowd(Golden.GetProperty("base"), _spike.Base());
        AssertCrowd(Golden.GetProperty("extra"), _spike.Extra());
        var newcomers = _spike.Newcomers(60);
        var want = Golden.GetProperty("newcomers");
        Assert.Equal(want.GetArrayLength(), newcomers.Count);
        var i = 0;
        foreach (var w in want.EnumerateArray())
        {
            var (day, hour, vm) = newcomers[i++];
            Assert.Equal(w.GetProperty("day").GetInt32(), day);
            Assert.Equal(w.GetProperty("hour").GetInt32(), hour);
            AssertVm(w.GetProperty("vm"), vm);
        }
        output.WriteLine($"base {_spike.Base().Count}, extra {_spike.Extra().Count}, newcomers {newcomers.Count}: all match");
    }

    [Fact]
    public void Rank_games_match_Python()
    {
        var crowd = _spike.Base();
        for (var n = 0; n < crowd.Count; n++)
        {
            var vm = crowd[n];
            if (n < 50)
                foreach (var d in new[] { 1, 2, 3 }) _spike.Play(vm, 202611, d, 1);
            else
            {
                foreach (var d in new[] { 1, 2 }) _spike.Play(vm, 202611, d, 1, joined: (2, 10));
                _spike.Play(vm, 202611, 3, 1, hour: 12);
            }
        }
        AssertCrowd(Golden.GetProperty("played"), crowd);
    }

    [Fact]
    public void Seeded_picks_and_club_points_match_Python()
    {
        var n = 0;
        foreach (var p in Golden.GetProperty("skill").EnumerateObject())
        {
            var vid = p.Name;
            Assert.True(p.Value.GetInt32() == Skill(vid), $"{vid} skill");
            Assert.Equal(Golden.GetProperty("personality").GetProperty(vid).GetString(), _spike.Personality(vid));
            Assert.Equal(Golden.GetProperty("style").GetProperty(vid).GetString(), _spike.Style(vid));
            Assert.Equal(Golden.GetProperty("region").GetProperty(vid).GetString(), _spike.Region(vid));
            var pts = Ints(Golden.GetProperty("club_points").GetProperty(vid));
            Assert.Equal(pts, new[] { ClubVmPoints(vid, 0, 20), ClubVmPoints(vid, 15, 20) });
            n++;
        }
        output.WriteLine($"{n} managers: skill, personality, style, region and club points match");
    }

    [Fact]
    public void Ai_clubs_match_Python()
    {
        var clubs = _spike.AiClubs(_spike.Base().Concat(_spike.Extra()));
        var want = Golden.GetProperty("clubs").EnumerateArray().ToArray();
        Assert.Equal(want.Length, clubs.Count);
        var members = 0;
        for (var i = 0; i < want.Length; i++)
        {
            var (w, c) = (want[i], clubs[i]);
            Assert.Equal(w.GetProperty("_id").GetString(), c.Id);
            Assert.Equal(w.GetProperty("name").GetString(), c.Name);
            Assert.Equal(w.GetProperty("created").GetInt64(), c.Created);
            Assert.Equal(w.GetProperty("color").GetInt32(), c.Color);
            Assert.Equal(w.GetProperty("allowjoin").GetBoolean(), c.AllowJoin);
            Assert.Equal(w.GetProperty("limit").GetInt32(), c.Limit);
            var wm = w.GetProperty("members").EnumerateArray()
                .Select(m => (m.GetProperty("id").GetString()!, m.GetProperty("joined").GetInt64(), m.GetProperty("grade").GetInt32()))
                .ToList();
            Assert.Equal(wm, c.Members);
            members += wm.Count;
        }
        output.WriteLine($"{clubs.Count} AI clubs, {members} members: all match");
    }

    [Fact]
    public void Market_prices_match_Python_to_the_last_bit()
    {
        foreach (var m in Golden.GetProperty("market").EnumerateArray())
        {
            var want = m.GetProperty("factor").GetDouble();
            var got = MarketFactor(m.GetProperty("spid").GetInt64(), m.GetProperty("grade").GetInt32(), m.GetProperty("day").GetInt32());
            Assert.True(BitConverter.DoubleToInt64Bits(want) == BitConverter.DoubleToInt64Bits(got), $"{m}: {want:R} vs {got:R}");
        }
    }
}
