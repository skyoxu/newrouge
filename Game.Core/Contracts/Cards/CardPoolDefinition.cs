using System.Collections.Generic;

namespace Game.Core.Contracts.Cards;

/// <summary>
/// Immutable card pool keyed by Act and encounter type.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032, ADR-0033.
/// </remarks>
public sealed record CardPoolDefinition(
    int ActId,
    string EncounterType,
    string PoolId,
    IReadOnlyDictionary<string, IReadOnlyList<string>> CardsByRarity
);
