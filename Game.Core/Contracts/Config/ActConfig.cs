using System.Text.Json;
using System.Text.Json.Serialization;

namespace Game.Core.Contracts.Config;

/// <summary>
/// Immutable act configuration loaded from JSON data files.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0006, ADR-0031, ADR-0021.
/// Overlay ref: docs/architecture/overlays/PRD-NEWROUGE-GAME-0001/08/08-Contracts-M1.md
/// </remarks>
public sealed record ActConfig(
    [property: JsonPropertyName("schema_version")] string SchemaVersion,
    [property: JsonPropertyName("act_id")] int ActId,
    [property: JsonPropertyName("node_graph")] JsonElement NodeGraph,
    [property: JsonPropertyName("pools")] JsonElement Pools,
    [property: JsonPropertyName("encounters")] JsonElement Encounters
);
