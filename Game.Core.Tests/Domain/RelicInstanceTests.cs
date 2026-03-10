using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Domain;

public class RelicInstanceTests
{
    // ACC:T30.5
    [Fact]
    public void ShouldExposeRequiredMembersOnRelicInstanceContract_WhenAcceptanceIsValidated()
    {
        var relicInstanceType = FindRelicInstanceContractType();

        relicInstanceType.Should().NotBeNull("RelicInstance contract must exist under Game.Core.Contracts.");
        ValidateRelicInstanceShape(relicInstanceType!).Should().BeTrue(
            "RelicInstance must publicly expose both 'instance_id' and 'modifiers'.");
    }

    [Fact]
    public void ShouldRejectContractShape_WhenInstanceIdIsMissing()
    {
        ValidateRelicInstanceShape(typeof(MissingInstanceIdContract)).Should().BeFalse(
            "acceptance must fail when instance_id is missing.");
    }

    [Fact]
    public void ShouldRejectContractShape_WhenModifiersIsMissing()
    {
        ValidateRelicInstanceShape(typeof(MissingModifiersContract)).Should().BeFalse(
            "acceptance must fail when modifiers is missing.");
    }

    private static Type? FindRelicInstanceContractType()
    {
        foreach (var assembly in AppDomain.CurrentDomain.GetAssemblies())
        {
            Type[] types;
            try
            {
                types = assembly.GetTypes();
            }
            catch (ReflectionTypeLoadException ex)
            {
                types = ex.Types.Where(t => t is not null).Cast<Type>().ToArray();
            }

            var found = types.FirstOrDefault(t =>
                t.Name == "RelicInstance" &&
                t.Namespace is not null &&
                t.Namespace.StartsWith("Game.Core.Contracts", StringComparison.Ordinal));

            if (found is not null)
            {
                return found;
            }
        }

        return null;
    }

    private static bool ValidateRelicInstanceShape(Type type)
    {
        return HasPublicFieldOrProperty(type, "instance_id") &&
               HasPublicFieldOrProperty(type, "modifiers");
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

    private sealed class MissingInstanceIdContract
    {
        public List<string> modifiers { get; } = new();
    }

    private sealed class MissingModifiersContract
    {
        public string instance_id { get; } = "id-1";
    }
}
