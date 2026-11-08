using System.Text.Json;

namespace FO3.Host.Tests;

internal static class Golden
{
    public static JsonElement Load(string name) =>
        JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory, "Golden", name))).RootElement;
}
