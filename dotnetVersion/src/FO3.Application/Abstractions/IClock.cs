namespace FO3.Application.Abstractions;

/// <summary>The time, injected so golden tests can replay a recorded session at its own moment.</summary>
public interface IClock
{
    DateTimeOffset UtcNow { get; }
}
