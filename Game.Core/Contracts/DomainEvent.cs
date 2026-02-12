namespace Game.Core.Contracts;

/// <summary>
/// Domain event envelope aligned with CloudEvents-style core attributes.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0004, ADR-0020.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record DomainEvent(
    string Type,
    string Source,
    string? DataJson,
    DateTimeOffset Timestamp,
    string Id,
    string SpecVersion = "1.0",
    string DataContentType = "application/json"
);

