using System.Numerics;
using System.Security.Cryptography;
using System.Text;

namespace FO3.Domain.Randomness;

/// <summary>
/// A bit-exact port of CPython's <c>random.Random</c>: the MT19937 core of
/// Modules/_randommodule.c and the methods of Lib/random.py that the Python server calls on a
/// seeded generator (random, getrandbits, randrange, randint, choice, choices, shuffle, sample,
/// uniform). The same seed gives the same draws as Python, so a virtual manager, an AI club or a
/// market price seeded from a string comes out the same after the move to .NET.
/// </summary>
/// <remarks>
/// Draw order matters as much as the algorithm: a ported caller must make the same calls in the
/// same order as the Python code (Python evaluates left to right, dict literals included).
/// <see cref="RandBelow"/> draws even for n = 1, as Python does (randint(0, 0) uses up a word).
/// </remarks>
public sealed class PyRandom
{
    private const int N = 624, M = 397;
    private const uint MatrixA = 0x9908b0dfu, UpperMask = 0x80000000u, LowerMask = 0x7fffffffu;

    private readonly uint[] _mt = new uint[N];
    private int _index = N + 1;

    /// <summary>Python <c>random.Random(s)</c> for a str seed (version 2: UTF-8 + SHA-512).</summary>
    public PyRandom(string seed) => Seed(seed);

    /// <summary>Python <c>random.Random(n)</c> for an int seed.</summary>
    public PyRandom(long seed) => Seed(new BigInteger(seed));

    /// <summary>Python <c>random.Random(n)</c> for an int seed of any size.</summary>
    public PyRandom(BigInteger seed) => Seed(seed);

    /// <summary>Python <c>seed(a)</c> for a str: int.from_bytes(a + sha512(a), "big").</summary>
    public void Seed(string seed)
    {
        var text = Encoding.UTF8.GetBytes(seed);
        var buf = new byte[text.Length + SHA512.HashSizeInBytes];
        text.CopyTo(buf, 0);
        SHA512.HashData(text).CopyTo(buf, text.Length);
        Seed(new BigInteger(buf, isUnsigned: true, isBigEndian: true));
    }

    /// <summary>Python <c>seed(n)</c> for an int: |n| split into 32-bit words, least significant first.</summary>
    public void Seed(BigInteger seed)
    {
        var n = BigInteger.Abs(seed);
        var bytes = n.IsZero ? [0] : n.ToByteArray(isUnsigned: true, isBigEndian: false);
        var key = new uint[Math.Max(1, (bytes.Length + 3) / 4)];
        for (var i = 0; i < bytes.Length; i++)
            key[i / 4] |= (uint)bytes[i] << (8 * (i % 4));
        InitByArray(key);
    }

    private void InitGenrand(uint s)
    {
        unchecked
        {
            _mt[0] = s;
            for (_index = 1; _index < N; _index++)
                _mt[_index] = 1812433253u * (_mt[_index - 1] ^ (_mt[_index - 1] >> 30)) + (uint)_index;
        }
    }

    private void InitByArray(uint[] key)
    {
        unchecked
        {
            InitGenrand(19650218u);
            int i = 1, j = 0;
            for (var k = Math.Max(N, key.Length); k > 0; k--)
            {
                _mt[i] = (_mt[i] ^ ((_mt[i - 1] ^ (_mt[i - 1] >> 30)) * 1664525u)) + key[j] + (uint)j;
                i++; j++;
                if (i >= N) { _mt[0] = _mt[N - 1]; i = 1; }
                if (j >= key.Length) j = 0;
            }
            for (var k = N - 1; k > 0; k--)
            {
                _mt[i] = (_mt[i] ^ ((_mt[i - 1] ^ (_mt[i - 1] >> 30)) * 1566083941u)) - (uint)i;
                i++;
                if (i >= N) { _mt[0] = _mt[N - 1]; i = 1; }
            }
            _mt[0] = 0x80000000u;
        }
    }

    /// <summary>The next 32-bit word (genrand_uint32).</summary>
    public uint NextUInt32()
    {
        uint y;
        if (_index >= N)
        {
            int kk;
            for (kk = 0; kk < N - M; kk++)
            {
                y = (_mt[kk] & UpperMask) | (_mt[kk + 1] & LowerMask);
                _mt[kk] = _mt[kk + M] ^ (y >> 1) ^ ((y & 1u) * MatrixA);
            }
            for (; kk < N - 1; kk++)
            {
                y = (_mt[kk] & UpperMask) | (_mt[kk + 1] & LowerMask);
                _mt[kk] = _mt[kk + (M - N)] ^ (y >> 1) ^ ((y & 1u) * MatrixA);
            }
            y = (_mt[N - 1] & UpperMask) | (_mt[0] & LowerMask);
            _mt[N - 1] = _mt[M - 1] ^ (y >> 1) ^ ((y & 1u) * MatrixA);
            _index = 0;
        }
        y = _mt[_index++];
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c5680u;
        y ^= (y << 15) & 0xefc60000u;
        y ^= y >> 18;
        return y;
    }

    /// <summary>Python <c>random()</c>: a float in [0, 1) from 53 random bits.</summary>
    public double Random()
    {
        var a = NextUInt32() >> 5;
        var b = NextUInt32() >> 6;
        return (a * 67108864.0 + b) * (1.0 / 9007199254740992.0);
    }

    /// <summary>Python <c>getrandbits(k)</c> for 0 &lt;= k &lt;= 64: words fill from the least significant.</summary>
    public ulong GetRandBits(int k)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(k);
        ArgumentOutOfRangeException.ThrowIfGreaterThan(k, 64);
        if (k == 0) return 0;
        if (k <= 32) return NextUInt32() >> (32 - k);
        ulong low = NextUInt32();
        ulong high = NextUInt32() >> (64 - k);
        return low | (high << 32);
    }

    /// <summary>Python <c>_randbelow(n)</c>: an int in [0, n), by rejection on n.bit_length() bits.</summary>
    public long RandBelow(long n)
    {
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(n);
        var k = 64 - BitOperations.LeadingZeroCount((ulong)n);
        var r = GetRandBits(k);
        while (r >= (ulong)n)
            r = GetRandBits(k);
        return (long)r;
    }

    /// <summary>Python <c>randrange(stop)</c>.</summary>
    public long RandRange(long stop) =>
        stop > 0 ? RandBelow(stop) : throw new ArgumentException("empty range for randrange()");

    /// <summary>Python <c>randrange(start, stop[, step])</c>.</summary>
    public long RandRange(long start, long stop, long step = 1)
    {
        var width = stop - start;
        if (step == 1)
            return width > 0 ? start + RandBelow(width) : throw new ArgumentException($"empty range in randrange({start}, {stop})");
        long n = step switch
        {
            > 0 => FloorDiv(width + step - 1, step),
            < 0 => FloorDiv(width + step + 1, step),
            _ => throw new ArgumentException("zero step for randrange()"),
        };
        if (n <= 0) throw new ArgumentException($"empty range in randrange({start}, {stop}, {step})");
        return start + step * RandBelow(n);
    }

    /// <summary>Python <c>randint(a, b)</c>: an int in [a, b].</summary>
    public long RandInt(long a, long b) => RandRange(a, b + 1);

    /// <summary><see cref="RandInt(long, long)"/> for int ranges.</summary>
    public int RandInt(int a, int b) => (int)RandRange(a, (long)b + 1);

    /// <summary>Python <c>uniform(a, b)</c>: a + (b - a) * random().</summary>
    public double Uniform(double a, double b) => a + (b - a) * Random();

    /// <summary>Python <c>choice(seq)</c>.</summary>
    public T Choice<T>(IReadOnlyList<T> seq) =>
        seq.Count > 0 ? seq[(int)RandBelow(seq.Count)] : throw new IndexOutOfRangeException("Cannot choose from an empty sequence");

    /// <summary>Python <c>shuffle(x)</c>, in place.</summary>
    public void Shuffle<T>(IList<T> x)
    {
        for (var i = x.Count - 1; i > 0; i--)
        {
            var j = (int)RandBelow(i + 1);
            (x[i], x[j]) = (x[j], x[i]);
        }
    }

    /// <summary>Python <c>sample(population, k)</c>: k distinct positions, in selection order.</summary>
    public List<T> Sample<T>(IReadOnlyList<T> population, int k)
    {
        var n = population.Count;
        if (k < 0 || k > n) throw new ArgumentException("Sample larger than population or is negative");
        var result = new List<T>(k);
        long setsize = 21;
        if (k > 5)
            setsize += IntPow(4, (int)Math.Ceiling(Math.Log(k * 3.0) / Math.Log(4.0)));
        if (n <= setsize)
        {
            var pool = population.ToList();
            for (var i = 0; i < k; i++)
            {
                var j = (int)RandBelow(n - i);
                result.Add(pool[j]);
                pool[j] = pool[n - i - 1];
            }
        }
        else
        {
            var selected = new HashSet<int>();
            for (var i = 0; i < k; i++)
            {
                var j = (int)RandBelow(n);
                while (selected.Contains(j))
                    j = (int)RandBelow(n);
                selected.Add(j);
                result.Add(population[j]);
            }
        }
        return result;
    }

    /// <summary>Python <c>choices(population, k=k)</c> (no weights): floor(random() * n) each.</summary>
    public List<T> Choices<T>(IReadOnlyList<T> population, int k = 1)
    {
        double n = population.Count;
        var result = new List<T>(k);
        for (var i = 0; i < k; i++)
            result.Add(population[(int)Math.Floor(Random() * n)]);
        return result;
    }

    /// <summary>
    /// Python <c>choices(population, weights, k=k)</c>: bisect_right over the running sums.
    /// Integer weights are exact as doubles (below 2^53), as Python's int sums compare exactly.
    /// </summary>
    public List<T> Choices<T>(IReadOnlyList<T> population, IReadOnlyList<double> weights, int k = 1)
    {
        var n = population.Count;
        if (weights.Count != n) throw new ArgumentException("The number of weights does not match the population");
        var cum = new double[n];
        double acc = 0;
        for (var i = 0; i < n; i++) cum[i] = acc = i == 0 ? weights[0] : acc + weights[i];
        var total = cum[n - 1];
        if (!(total > 0.0)) throw new ArgumentException("Total of weights must be greater than zero");
        if (!double.IsFinite(total)) throw new ArgumentException("Total of weights must be finite");
        var result = new List<T>(k);
        for (var i = 0; i < k; i++)
            result.Add(population[BisectRight(cum, Random() * total, 0, n - 1)]);
        return result;
    }

    private static int BisectRight(double[] a, double x, int lo, int hi)
    {
        while (lo < hi)
        {
            var mid = (lo + hi) / 2;
            if (x < a[mid]) hi = mid;
            else lo = mid + 1;
        }
        return lo;
    }

    private static long FloorDiv(long a, long b)
    {
        var q = a / b;
        return (a % b != 0) && ((a < 0) != (b < 0)) ? q - 1 : q;
    }

    private static long IntPow(long b, int e)
    {
        long r = 1;
        for (var i = 0; i < e; i++) r *= b;
        return r;
    }
}
