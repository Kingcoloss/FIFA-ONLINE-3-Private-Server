using System.Text;
using System.Text.Json.Nodes;
using FO3.Infrastructure.State;

namespace FO3.Host.Tests;

public sealed class JsonFileStateStoreTests : IDisposable
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "fo3-state-" + Guid.NewGuid().ToString("N"));

    public void Dispose()
    {
        if (Directory.Exists(_dir)) Directory.Delete(_dir, true);
    }

    [Fact]
    public async Task No_file_reads_as_Pythons_empty_state()
    {
        var store = new JsonFileStateStore(Path.Combine(_dir, "state.json"));
        Assert.True(JsonNode.DeepEquals(JsonFileStateStore.Empty(), await store.LoadAsync()));
    }

    [Fact]
    public async Task A_save_is_ASCII_json_dump_text_and_reads_back()
    {
        var path = Path.Combine(_dir, "state.json");
        var store = new JsonFileStateStore(path);
        var state = new JsonObject
        {
            ["coaches"] = new JsonArray(new JsonObject { ["name"] = "ผู้จัดการ", ["ep"] = 1500000, ["rate"] = 0.25 }),
            ["defaultcoachid"] = "c1",
            ["teams"] = new JsonObject(),
        };
        await store.SaveAsync(state);
        var text = await File.ReadAllBytesAsync(path);
        Assert.All(text, b => Assert.True(b < 0x80));
        // json.dump(st, f) of the same state
        Assert.Equal("{\"coaches\": [{\"name\": \"\\u0e1c\\u0e39\\u0e49\\u0e08\\u0e31\\u0e14\\u0e01\\u0e32\\u0e23\", \"ep\": 1500000, \"rate\": 0.25}], \"defaultcoachid\": \"c1\", \"teams\": {}}",
            Encoding.ASCII.GetString(text));
        Assert.True(JsonNode.DeepEquals(state, await new JsonFileStateStore(path).LoadAsync()));
        Assert.False(File.Exists(path + ".net.tmp"));
    }
}
