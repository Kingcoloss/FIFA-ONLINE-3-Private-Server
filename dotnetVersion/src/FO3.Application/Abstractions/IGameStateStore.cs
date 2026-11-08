using System.Text.Json.Nodes;

namespace FO3.Application.Abstractions;

/// <summary>
/// The game state (every manager, club, item and season the client sees). During the move it is
/// the Python server's gamedata/state.json; later SQLite. Callers get a copy: a change is only
/// kept by <see cref="SaveAsync"/>.
/// </summary>
public interface IGameStateStore
{
    /// <summary>The state as stored now, or an empty object when there is none yet.</summary>
    Task<JsonObject> LoadAsync(CancellationToken ct = default);

    /// <summary>Replace the stored state in one step (a reader never sees half a file).</summary>
    Task SaveAsync(JsonObject state, CancellationToken ct = default);
}
