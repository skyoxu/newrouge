using System.Collections.Generic;

namespace Game.Core.Contracts.Content;

/// <summary>
/// Relic instance in a run inventory.
/// </summary>
public sealed record RelicInstance(
    string instance_id,
    IReadOnlyList<string> modifiers
);
