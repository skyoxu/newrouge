using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class ActConfigLoaderSchemaVersionTests
{
    // ACC:T28.4
    [Fact]
    public void ShouldFail_WhenSchemaVersionIsMissing()
    {
        var loader = new ActConfigLoader();
        const string json = """
                            {
                              "act_id": 1,
                              "node_graph": { "start": "N-1-1" },
                              "pools": { "normal": ["enemy_a"] },
                              "encounters": [{ "id": "enc-1-1" }]
                            }
                            """;

        var result = loader.LoadFromJson(json, "schema-missing");

        result.IsSuccess.Should().BeFalse();
        result.ErrorCode.Should().Be("schema_version_missing");
        result.ErrorMessage.Should().Contain("schema_version");
    }

    // ACC:T28.5
    [Fact]
    public void ShouldFail_WhenSchemaVersionIsUnsupported()
    {
        var loader = new ActConfigLoader();
        const string json = """
                            {
                              "schema_version": "2.0",
                              "act_id": 1,
                              "node_graph": { "start": "N-1-1" },
                              "pools": { "normal": ["enemy_a"] },
                              "encounters": [{ "id": "enc-1-1" }]
                            }
                            """;

        var result = loader.LoadFromJson(json, "schema-unsupported");

        result.IsSuccess.Should().BeFalse();
        result.ErrorCode.Should().Be("schema_version_unsupported");
        result.ErrorMessage.Should().Contain("2.0");
    }

    // ACC:T28.4
    [Fact]
    public void ShouldFail_WhenSchemaVersionIsUnknown()
    {
        var loader = new ActConfigLoader();
        const string json = """
                            {
                              "schema_version": "preview-x",
                              "act_id": 1,
                              "node_graph": { "start": "N-1-1" },
                              "pools": { "normal": ["enemy_a"] },
                              "encounters": [{ "id": "enc-1-1" }]
                            }
                            """;

        var result = loader.LoadFromJson(json, "schema-unknown");

        result.IsSuccess.Should().BeFalse();
        result.ErrorCode.Should().Be("schema_version_unsupported");
        result.ErrorMessage.Should().Contain("preview-x");
    }
}
