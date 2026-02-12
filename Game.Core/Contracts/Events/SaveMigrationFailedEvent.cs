namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when save schema migration fails.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record SaveMigrationFailedEvent(
    string RunId,
    string FromSchema,
    string ToSchema,
    string ReasonCode,
    DateTimeOffset FailedAt
)
{
    public const string EventType = EventTypes.SaveMigrationFailed;
}
