using System.Text.Json;
using Game.Core.Contracts.Config;

namespace Game.Core.Services;

/// <summary>
/// Loads act configuration JSON into strongly typed contracts.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0006, ADR-0031, ADR-0021.
/// </remarks>
public sealed class ActConfigLoader
{
    private static readonly JsonSerializerOptions SerializerOptions = new()
    {
        PropertyNameCaseInsensitive = false,
    };

    /// <summary>
    /// Load an <see cref="ActConfig"/> from a JSON file.
    /// </summary>
    public ActConfigLoadResult LoadFromFile(string filePath)
    {
        if (string.IsNullOrWhiteSpace(filePath))
        {
            return ActConfigLoadResult.Failure("invalid_path", "File path must be non-empty.", "<empty-path>");
        }

        try
        {
            var json = File.ReadAllText(filePath);
            return LoadFromJson(json, filePath);
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
        {
            return ActConfigLoadResult.Failure("read_failed", $"Failed to read act config file: {ex.Message}", filePath);
        }
    }

    /// <summary>
    /// Load an <see cref="ActConfig"/> from JSON text.
    /// </summary>
    public ActConfigLoadResult LoadFromJson(string json, string source = "<json>")
    {
        if (string.IsNullOrWhiteSpace(json))
        {
            return ActConfigLoadResult.Failure("empty_json", "Act config JSON must be non-empty.", source);
        }

        ActConfig? config;
        try
        {
            config = JsonSerializer.Deserialize<ActConfig>(json, SerializerOptions);
        }
        catch (JsonException ex)
        {
            return ActConfigLoadResult.Failure("json_parse_failed", $"Invalid JSON payload: {ex.Message}", source);
        }

        if (config is null)
        {
            return ActConfigLoadResult.Failure("null_config", "JSON payload resolved to null ActConfig.", source);
        }

        if (string.IsNullOrWhiteSpace(config.SchemaVersion))
        {
            return ActConfigLoadResult.Failure("schema_version_missing", "Act config must include non-empty schema_version.", source);
        }

        if (!string.Equals(config.SchemaVersion, "1.0", StringComparison.Ordinal))
        {
            return ActConfigLoadResult.Failure(
                "schema_version_unsupported",
                $"Unsupported schema_version '{config.SchemaVersion}'. Expected '1.0'.",
                source);
        }

        if (config.ActId <= 0)
        {
            return ActConfigLoadResult.Failure("invalid_act_id", "act_id must be greater than 0.", source);
        }

        if (config.NodeGraph.ValueKind is JsonValueKind.Undefined or JsonValueKind.Null)
        {
            return ActConfigLoadResult.Failure("node_graph_missing", "node_graph must be provided.", source);
        }

        if (config.Pools.ValueKind is JsonValueKind.Undefined or JsonValueKind.Null)
        {
            return ActConfigLoadResult.Failure("pools_missing", "pools must be provided.", source);
        }

        if (config.Encounters.ValueKind is JsonValueKind.Undefined or JsonValueKind.Null)
        {
            return ActConfigLoadResult.Failure("encounters_missing", "encounters must be provided.", source);
        }

        return ActConfigLoadResult.Success(config, source);
    }
}
