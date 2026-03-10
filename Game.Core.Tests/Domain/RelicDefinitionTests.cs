using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Game.Core.Contracts.Content;
using Xunit;

namespace Game.Core.Tests.Domain;

public class RelicDefinitionTests
{
    // ACC:T30.4
    [Fact]
    [Trait("acceptance", "ACC:T30.4")]
    public void ShouldExposeCoreContractMembers_WhenInspectingRelicDefinition()
    {
        var type = typeof(RelicDefinition);

        type.Should().NotBeNull();
        type.Namespace.Should().Be("Game.Core.Contracts.Content");

        var members = GetPublicFieldAndPropertyNames(type)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);

        members.Should().BeEquivalentTo(new[] { "relic_id", "name_key", "description_key", "tags" });
        members.Count.Should().BeGreaterOrEqualTo(4);
    }

    [Fact]
    public void ShouldBeReferenceRecordStyleContract_WhenUsingRelicDefinitionType()
    {
        var type = typeof(RelicDefinition);

        type.IsClass.Should().BeTrue();
        type.IsSealed.Should().BeTrue();
    }

    [Fact]
    public void ShouldRejectContractShape_WhenDescriptionKeyIsMissing()
    {
        ValidateRelicDefinitionShape(typeof(MissingDescriptionKeyContract)).Should().BeFalse(
            "acceptance must fail when description_key is missing.");
    }

    [Fact]
    public void ShouldRejectContractShape_WhenTagsIsMissing()
    {
        ValidateRelicDefinitionShape(typeof(MissingTagsContract)).Should().BeFalse(
            "acceptance must fail when tags is missing.");
    }

    private static bool ValidateRelicDefinitionShape(Type type)
    {
        return HasPublicFieldOrProperty(type, "relic_id") &&
               HasPublicFieldOrProperty(type, "name_key") &&
               HasPublicFieldOrProperty(type, "description_key") &&
               HasPublicFieldOrProperty(type, "tags");
    }

    private static bool HasPublicFieldOrProperty(Type type, string memberName)
    {
        const BindingFlags Flags = BindingFlags.Public | BindingFlags.Instance;

        var field = type.GetField(memberName, Flags);
        if (field is not null)
        {
            return true;
        }

        var property = type.GetProperty(memberName, Flags);
        return property is not null;
    }

    private static IEnumerable<string> GetPublicFieldAndPropertyNames(Type type)
    {
        var propertyNames = type
            .GetProperties(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
            .Select(p => p.Name);

        var fieldNames = type
            .GetFields(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static)
            .Select(f => f.Name);

        return propertyNames.Concat(fieldNames);
    }

    private sealed class MissingDescriptionKeyContract
    {
        public string relic_id { get; } = "id-1";
        public string name_key { get; } = "name-1";
        public IReadOnlyList<string> tags { get; } = Array.Empty<string>();
    }

    private sealed class MissingTagsContract
    {
        public string relic_id { get; } = "id-1";
        public string name_key { get; } = "name-1";
        public string description_key { get; } = "desc-1";
    }
}
