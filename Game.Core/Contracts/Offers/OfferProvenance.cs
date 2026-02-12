namespace Game.Core.Contracts.Offers;

/// <summary>
/// Deterministic provenance for reproducible offer generation.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032.
/// </remarks>
public sealed record OfferProvenance(
    OfferSourceType SourceType,
    string SourceId,
    int Act,
    int Floor,
    string NodeId,
    int Difficulty,
    string RngStream,
    long StreamPosition
);

