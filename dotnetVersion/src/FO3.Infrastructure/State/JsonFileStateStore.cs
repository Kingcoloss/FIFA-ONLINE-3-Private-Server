using System.Text;
using System.Text.Json.Nodes;
using FO3.Application.Abstractions;
using FO3.Infrastructure.Serialization;

namespace FO3.Infrastructure.State;

/// <summary>
/// <see cref="IGameStateStore"/> on a JSON file, the Python server's gamedata/state.json while
/// both servers run. A save writes a temporary file next to it (its own name: Python uses
/// state.json.tmp) and moves it over the old one, so the other process reads the old state or the
/// new one, never a torn file. The text is what Python's json.dump writes (ASCII only, ", " and
/// ": "): Python opens the file in the locale's encoding. A read retries for a moment while the
/// other process holds the file.
/// </summary>
public sealed class JsonFileStateStore(string path) : IGameStateStore
{
    private readonly SemaphoreSlim _gate = new(1, 1);

    public string Path { get; } = System.IO.Path.GetFullPath(path);

    /// <summary>What Python's _state() returns when there is no file yet.</summary>
    public static JsonObject Empty() => new() { ["coaches"] = new JsonArray(), ["defaultcoachid"] = "", ["teams"] = new JsonObject() };

    public async Task<JsonObject> LoadAsync(CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct);
        try
        {
            for (var attempt = 0; ; attempt++)
            {
                try
                {
                    if (!File.Exists(Path)) return Empty();
                    await using var f = new FileStream(Path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
                    return JsonNode.Parse(f) as JsonObject ?? throw new InvalidDataException($"{Path}: not a JSON object");
                }
                catch (IOException) when (attempt < 40)
                {
                    await Task.Delay(50, ct);
                }
            }
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task SaveAsync(JsonObject state, CancellationToken ct = default)
    {
        await _gate.WaitAsync(ct);
        try
        {
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(Path)!);
            var tmp = Path + ".net.tmp";
            await File.WriteAllTextAsync(tmp, PyJson.Dumps(state, compact: false), Encoding.ASCII, ct);
            for (var attempt = 0; ; attempt++)
            {
                try
                {
                    File.Move(tmp, Path, overwrite: true);
                    return;
                }
                catch (IOException) when (attempt < 40)
                {
                    await Task.Delay(50, ct);
                }
                catch (UnauthorizedAccessException) when (attempt < 40) // Windows: a reader holds it
                {
                    await Task.Delay(50, ct);
                }
            }
        }
        finally
        {
            _gate.Release();
        }
    }
}
