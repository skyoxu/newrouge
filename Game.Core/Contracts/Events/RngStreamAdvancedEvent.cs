namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when deterministic RNG stream advances.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record RngStreamAdvancedEvent(
    string RunId,
    string StreamName,
    long PositionBefore,
    long PositionAfter,
    DateTimeOffset AdvancedAt
)
{
    public const string EventType = EventTypes.RngStreamAdvanced;
}
