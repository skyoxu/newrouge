using FluentAssertions;
using Game.Core.Services;
using Xunit;

namespace Game.Core.Tests.Services;

public sealed class ActConfigLoaderTests
{
    // ACC:T28.5
    [Fact]
    public void ShouldLoadActConfig_WhenJsonIsValid()
    {
        var loader = new ActConfigLoader();
        const string json = """
                            {
                              "schema_version": "1.0",
                              "act_id": 2,
                              "node_graph": { "start": "N-2-1", "nodes": ["N-2-1", "N-2-2"] },
                              "pools": { "normal": ["enemy_a"], "elite": ["enemy_b"] },
                              "encounters": [{ "id": "enc-2-1", "type": "combat" }]
                            }
                            """;

        var result = loader.LoadFromJson(json, "in-memory");

        result.IsSuccess.Should().BeTrue();
        result.Config.Should().NotBeNull();
        result.Config!.SchemaVersion.Should().Be("1.0");
        result.Config.ActId.Should().Be(2);
        result.Config.NodeGraph.GetProperty("start").GetString().Should().Be("N-2-1");
        result.Config.Pools.GetProperty("normal")[0].GetString().Should().Be("enemy_a");
        result.Config.Encounters.GetArrayLength().Should().Be(1);
        result.Config.Encounters[0].GetProperty("id").GetString().Should().Be("enc-2-1");
        result.Config.Encounters[0].GetProperty("type").GetString().Should().Be("combat");
    }

    [Theory]
    [InlineData("{\"schema_version\":\"1.0\",\"act_id\":\"bad\",\"node_graph\":{},\"pools\":{},\"encounters\":[]}", "json_parse_failed")]
    [InlineData("{\"schema_version\":\"1.0\",\"act_id\":1,\"node_graph\":null,\"pools\":{},\"encounters\":[]}", "node_graph_missing")]
    [InlineData("{\"schema_version\":\"1.0\",\"act_id\":1,\"node_graph\":{},\"pools\":null,\"encounters\":[]}", "pools_missing")]
    [InlineData("{\"schema_version\":\"1.0\",\"act_id\":1,\"node_graph\":{},\"pools\":{},\"encounters\":null}", "encounters_missing")]
    [InlineData("{\"schema_version\":\"1.0\",\"act_id\":0,\"node_graph\":{},\"pools\":{},\"encounters\":[]}", "invalid_act_id")]
    [InlineData("{\"schema_version\":\"1.0\",\"act_id\":1,\"node_graph\":{},\"pools\":{},\"encounters\":[}", "json_parse_failed")]
    public void ShouldFailWithDeterministicErrorCode_WhenPayloadIsInvalid(string json, string expectedCode)
    {
        var loader = new ActConfigLoader();

        var result = loader.LoadFromJson(json, "invalid-json");

        result.IsSuccess.Should().BeFalse();
        result.Config.Should().BeNull();
        result.ErrorCode.Should().Be(expectedCode);
        result.ErrorMessage.Should().NotBeNullOrWhiteSpace();
        result.Source.Should().Be("invalid-json");
    }

    // ACC:T28.6
    [Theory]
    [InlineData("{\"schema_version\":\"1.0\",\"act_id\":1,\"pools\":{},\"encounters\":[]}", "node_graph_missing")]
    [InlineData("{\"schema_version\":\"1.0\",\"act_id\":1,\"node_graph\":{},\"encounters\":[]}", "pools_missing")]
    [InlineData("{\"schema_version\":\"1.0\",\"act_id\":1,\"node_graph\":{},\"pools\":{}}", "encounters_missing")]
    public void ShouldFail_WhenRequiredFieldIsMissing(string json, string expectedCode)
    {
        var loader = new ActConfigLoader();

        var result = loader.LoadFromJson(json, "missing-required-field");

        result.IsSuccess.Should().BeFalse();
        result.Config.Should().BeNull();
        result.ErrorCode.Should().Be(expectedCode);
        result.ErrorMessage.Should().NotBeNullOrWhiteSpace();
    }

    // ACC:T28.7
    [Fact]
    public void ShouldKeepConfigsIsolated_WhenLoadingDifferentActsSequentially()
    {
        var loader = new ActConfigLoader();
        const string act1Json = """
                                {
                                  "schema_version": "1.0",
                                  "act_id": 1,
                                  "node_graph": { "start": "N-1-1" },
                                  "pools": { "normal": ["enemy_a"] },
                                  "encounters": [{ "id": "enc-1-1", "type": "combat" }]
                                }
                                """;
        const string act2Json = """
                                {
                                  "schema_version": "1.0",
                                  "act_id": 2,
                                  "node_graph": { "start": "N-2-1" },
                                  "pools": { "normal": ["enemy_b"] },
                                  "encounters": [{ "id": "enc-2-1", "type": "event" }]
                                }
                                """;

        var first = loader.LoadFromJson(act1Json, "act-1");
        var second = loader.LoadFromJson(act2Json, "act-2");

        first.IsSuccess.Should().BeTrue();
        second.IsSuccess.Should().BeTrue();
        first.Config!.ActId.Should().Be(1);
        second.Config!.ActId.Should().Be(2);
        first.Config.NodeGraph.GetProperty("start").GetString().Should().Be("N-1-1");
        second.Config.NodeGraph.GetProperty("start").GetString().Should().Be("N-2-1");
        first.Config.Pools.GetProperty("normal")[0].GetString().Should().Be("enemy_a");
        second.Config.Pools.GetProperty("normal")[0].GetString().Should().Be("enemy_b");
        first.Config.Encounters[0].GetProperty("id").GetString().Should().Be("enc-1-1");
        second.Config.Encounters[0].GetProperty("id").GetString().Should().Be("enc-2-1");
    }
}
