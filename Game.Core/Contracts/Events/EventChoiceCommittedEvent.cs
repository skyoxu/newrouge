using System.Collections.Generic;

namespace Game.Core.Contracts.Events;

/// <summary>
/// Raised when an event option is committed and made deterministic.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0032.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record EventChoiceCommittedEvent(
    string RunId,
    string EventId,
    string OptionId,
    string ChoiceResultId,
    DateTimeOffset CommittedAt,
    string ResultSummary = "",
    IReadOnlyDictionary<string, int>? NumericChanges = null
)
{
    public const string EventType = EventTypes.EventChoiceCommitted;
}
