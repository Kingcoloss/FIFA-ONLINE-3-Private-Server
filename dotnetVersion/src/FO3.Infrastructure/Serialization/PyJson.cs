using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;

namespace FO3.Infrastructure.Serialization;

/// <summary>
/// JSON text exactly as Python's <c>json.dumps</c> writes it (ensure_ascii, key order kept), so
/// files and frames the Python server reads or compares stay the same byte for byte: non-ASCII
/// as lowercase \uXXXX, floats as Python's repr, and either the compact separators
/// (<c>separators=(",", ":")</c>) or the default ", " / ": ".
/// </summary>
public static class PyJson
{
    public static string Dumps(JsonNode? node, bool compact = true)
    {
        var sb = new StringBuilder();
        Write(sb, node, compact ? "," : ", ", compact ? ":" : ": ");
        return sb.ToString();
    }

    private static void Write(StringBuilder sb, JsonNode? node, string item, string key)
    {
        switch (node)
        {
            case null:
                sb.Append("null");
                break;
            case JsonObject o:
                sb.Append('{');
                var first = true;
                foreach (var (k, v) in o)
                {
                    if (!first) sb.Append(item);
                    first = false;
                    WriteString(sb, k);
                    sb.Append(key);
                    Write(sb, v, item, key);
                }
                sb.Append('}');
                break;
            case JsonArray a:
                sb.Append('[');
                for (var i = 0; i < a.Count; i++)
                {
                    if (i > 0) sb.Append(item);
                    Write(sb, a[i], item, key);
                }
                sb.Append(']');
                break;
            case JsonValue v:
                WriteValue(sb, v);
                break;
        }
    }

    private static void WriteValue(StringBuilder sb, JsonValue v)
    {
        if (v.TryGetValue(out JsonElement e))
        {
            switch (e.ValueKind)
            {
                case JsonValueKind.String: WriteString(sb, e.GetString()!); return;
                case JsonValueKind.True: sb.Append("true"); return;
                case JsonValueKind.False: sb.Append("false"); return;
                case JsonValueKind.Null: sb.Append("null"); return;
                case JsonValueKind.Number: WriteNumberText(sb, e.GetRawText()); return;
            }
        }
        if (v.TryGetValue(out string? s)) { WriteString(sb, s); return; }
        if (v.TryGetValue(out bool b)) { sb.Append(b ? "true" : "false"); return; }
        if (v.TryGetValue(out double d)) { sb.Append(FloatRepr(d)); return; }
        if (v.TryGetValue(out float f)) { sb.Append(FloatRepr(f)); return; }
        if (v.TryGetValue(out decimal m)) { sb.Append(FloatRepr((double)m)); return; }
        // the integer types
        sb.Append(Convert.ToString(v.GetValue<object>(), CultureInfo.InvariantCulture));
    }

    /// <summary>A parsed number: an integer as written; a float as Python reads and re-writes it.</summary>
    private static void WriteNumberText(StringBuilder sb, string raw)
    {
        if (raw.AsSpan().IndexOfAny(".eE") < 0)
            sb.Append(raw);
        else
            sb.Append(FloatRepr(double.Parse(raw, CultureInfo.InvariantCulture)));
    }

    private static void WriteString(StringBuilder sb, string s)
    {
        sb.Append('"');
        foreach (var c in s)
        {
            switch (c)
            {
                case '"': sb.Append("\\\""); break;
                case '\\': sb.Append("\\\\"); break;
                case '\n': sb.Append("\\n"); break;
                case '\r': sb.Append("\\r"); break;
                case '\t': sb.Append("\\t"); break;
                case '\b': sb.Append("\\b"); break;
                case '\f': sb.Append("\\f"); break;
                default:
                    if (c >= ' ' && c <= '~') sb.Append(c);
                    else sb.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                    break;
            }
        }
        sb.Append('"');
    }

    /// <summary>Python's repr(float): the shortest round-trip digits, positional for exponents -4..15.</summary>
    public static string FloatRepr(double d)
    {
        if (double.IsNaN(d)) return "NaN";
        if (double.IsPositiveInfinity(d)) return "Infinity";
        if (double.IsNegativeInfinity(d)) return "-Infinity";
        if (d == 0) return double.IsNegative(d) ? "-0.0" : "0.0";

        // "R" gives the shortest round-trip digits; take them apart into sign, digits and exponent
        var shortest = d.ToString("R", CultureInfo.InvariantCulture);
        var neg = shortest.StartsWith('-');
        if (neg) shortest = shortest[1..];
        var ePos = shortest.IndexOfAny(['E', 'e']);
        var mant = ePos >= 0 ? shortest[..ePos] : shortest;
        var e10 = ePos >= 0 ? int.Parse(shortest[(ePos + 1)..], CultureInfo.InvariantCulture) : 0;
        var dot = mant.IndexOf('.');
        var intPart = dot >= 0 ? mant[..dot] : mant;
        var frac = dot >= 0 ? mant[(dot + 1)..] : "";
        var digits = (intPart + frac).TrimStart('0');
        var lead = (intPart + frac).Length - digits.Length; // zeros before the first digit
        var exp = intPart.Length - 1 - lead + e10;              // exponent of the first significant digit
        digits = digits.TrimEnd('0');
        if (digits.Length == 0) digits = "0";

        var sb = new StringBuilder();
        if (neg) sb.Append('-');
        if (exp >= -4 && exp < 16)
        {
            if (exp < 0)
                sb.Append("0.").Append('0', -exp - 1).Append(digits);
            else if (digits.Length <= exp + 1)
                sb.Append(digits).Append('0', exp + 1 - digits.Length).Append(".0");
            else
                sb.Append(digits, 0, exp + 1).Append('.').Append(digits, exp + 1, digits.Length - exp - 1);
        }
        else
        {
            sb.Append(digits[0]);
            if (digits.Length > 1) sb.Append('.').Append(digits, 1, digits.Length - 1);
            sb.Append('e').Append(exp < 0 ? '-' : '+').Append(Math.Abs(exp).ToString("00", CultureInfo.InvariantCulture));
        }
        return sb.ToString();
    }
}
