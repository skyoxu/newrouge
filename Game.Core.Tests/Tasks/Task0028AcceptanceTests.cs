using System;
using System.IO;
using System.Text;
using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Tasks;

[Trait("task", "T28")]
[Trait("adr", "ADR-0006")]
[Trait("adr", "ADR-0031")]
[Trait("adr", "ADR-0021")]
public sealed class Task0028AcceptanceTests
{
    // ACC:T28.1
    [Fact]
    public void ShouldPreserveNodeGraphPoolsAndEncounters_WhenActConfigLoadsSuccessfully()
    {
        var loader = new ActConfigLoader();
        const string json = """
                            {
                              "schema_version": "1.0",
                              "act_id": 3,
                              "node_graph": { "start": "N-3-1", "edges": [["N-3-1", "N-3-2"]] },
                              "pools": { "normal": ["enemy_a", "enemy_b"] },
                              "encounters": [{ "id": "enc-3-1", "type": "event" }]
                            }
                            """;

        var result = loader.LoadFromJson(json, "acc-t28-memory");

        result.IsSuccess.Should().BeTrue();
        result.Config.Should().NotBeNull();
        result.Config!.ActId.Should().Be(3);
        result.Config.NodeGraph.GetProperty("start").GetString().Should().Be("N-3-1");
        result.Config.Pools.GetProperty("normal").GetArrayLength().Should().Be(2);
        result.Config.Encounters.GetArrayLength().Should().Be(1);
    }

    // ACC:T28.3
    [Fact]
    public void ShouldReturnFailureResult_WhenFileReadFails()
    {
        var loader = new ActConfigLoader();
        var missingPath = Path.Combine(Path.GetTempPath(), "newrouge-task28", "missing-act.json");

        var result = loader.LoadFromFile(missingPath);

        result.IsSuccess.Should().BeFalse();
        result.Config.Should().BeNull();
        result.ErrorCode.Should().Be("read_failed");
        result.ErrorMessage.Should().Contain("Failed to read");
    }

    // ACC:T28.3
    [Fact]
    public void ShouldReturnFailureResult_WhenFileDeserializeFails()
    {
        var loader = new ActConfigLoader();
        var directory = Path.Combine(Path.GetTempPath(), "newrouge-task28");
        Directory.CreateDirectory(directory);
        var filePath = Path.Combine(directory, "invalid-act.json");
        File.WriteAllText(filePath, "{ \"schema_version\": \"1.0\", \"act_id\": 1, \"node_graph\": {", Encoding.UTF8);

        try
        {
            var result = loader.LoadFromFile(filePath);

            result.IsSuccess.Should().BeFalse();
            result.Config.Should().BeNull();
            result.ErrorCode.Should().Be("json_parse_failed");
            result.ErrorMessage.Should().Contain("Invalid JSON payload");
            result.Source.Should().Be(filePath);
        }
        finally
        {
            if (File.Exists(filePath))
            {
                File.Delete(filePath);
            }
        }
    }

    // ACC:T28.2
    [Fact]
    public void ShouldLoadFromFileSuccessfully_WhenFileContainsValidActConfig()
    {
        var loader = new ActConfigLoader();
        var directory = Path.Combine(Path.GetTempPath(), "newrouge-task28");
        Directory.CreateDirectory(directory);
        var filePath = Path.Combine(directory, "valid-act.json");
        const string json = """
                            {
                              "schema_version": "1.0",
                              "act_id": 7,
                              "node_graph": { "start": "N-7-1", "edges": [["N-7-1", "N-7-2"]] },
                              "pools": { "normal": ["enemy_a"] },
                              "encounters": [{ "id": "enc-7-1", "type": "combat" }]
                            }
                            """;
        File.WriteAllText(filePath, json, Encoding.UTF8);

        try
        {
            var result = loader.LoadFromFile(filePath);

            result.IsSuccess.Should().BeTrue();
            result.ErrorCode.Should().BeNullOrWhiteSpace();
            result.Config.Should().NotBeNull();
            result.Config!.ActId.Should().Be(7);
            result.Config.SchemaVersion.Should().Be("1.0");
            result.Config.NodeGraph.GetProperty("start").GetString().Should().Be("N-7-1");
            result.Source.Should().Be(filePath);
        }
        finally
        {
            if (File.Exists(filePath))
            {
                File.Delete(filePath);
            }
        }
    }

    // ACC:T28.4
    [Fact]
    public void ShouldExposeAssertableErrorMessage_WhenSchemaVersionValidationFails()
    {
        var loader = new ActConfigLoader();
        const string json = """
                            {
                              "schema_version": "legacy",
                              "act_id": 1,
                              "node_graph": {},
                              "pools": {},
                              "encounters": []
                            }
                            """;

        var result = loader.LoadFromJson(json, "acc-t28-schema");

        result.IsSuccess.Should().BeFalse();
        result.ErrorCode.Should().Be("schema_version_unsupported");
        result.ErrorMessage.Should().Contain("legacy");
    }

    // ACC:T28.4
    [Fact]
    public void ShouldReturnSchemaVersionUnsupported_WhenLoadFromFileContainsUnsupportedSchemaVersion()
    {
        var loader = new ActConfigLoader();
        var directory = Path.Combine(Path.GetTempPath(), "newrouge-task28");
        Directory.CreateDirectory(directory);
        var filePath = Path.Combine(directory, "unsupported-schema-act.json");
        const string json = """
                            {
                              "schema_version": "2.0",
                              "act_id": 1,
                              "node_graph": {},
                              "pools": {},
                              "encounters": []
                            }
                            """;
        File.WriteAllText(filePath, json, Encoding.UTF8);

        try
        {
            var result = loader.LoadFromFile(filePath);

            result.IsSuccess.Should().BeFalse();
            result.Config.Should().BeNull();
            result.ErrorCode.Should().Be("schema_version_unsupported");
            result.ErrorMessage.Should().Contain("2.0");
            result.Source.Should().Be(filePath);
        }
        finally
        {
            if (File.Exists(filePath))
            {
                File.Delete(filePath);
            }
        }
    }

}
