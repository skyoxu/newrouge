using System.Collections.Generic;

namespace Game.Core.Contracts.Content;

/// <summary>
/// Relic definition metadata.
/// </summary>
public sealed record RelicDefinition(
    string relic_id,
    string name_key,
    string description_key,
    IReadOnlyList<string> tags
);
