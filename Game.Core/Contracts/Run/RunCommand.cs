namespace Game.Core.Contracts.Run;

/// <summary>
/// Command that advances deterministic run state.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0032, ADR-0021.
/// </remarks>
public sealed record RunCommand(
    string CommandId,
    string CommandType,
    string Issuer,
    string PayloadJson,
    DateTimeOffset IssuedAt
);

