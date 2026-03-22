using NewRouge.Core.Conventions;
using Xunit;

namespace Game.Core.Tests.Conventions;

public sealed class NamespaceConventionsTests
{
    [Theory]
    [InlineData("Game.Core.Services.InventoryService", true)]
    [InlineData("NewRouge.Core.Services.InventoryService", false)]
    [InlineData("", false)]
    [InlineData("   ", false)]
    [InlineData(null, false)]
    public void Should_EvaluateLegacyPrefix_WhenCallingIsLegacy(string? namespaceValue, bool expected)
    {
        var actual = NamespaceConventions.IsLegacy(namespaceValue!);

        Assert.Equal(expected, actual);
    }

    [Theory]
    [InlineData("NewRouge.Core.Services.InventoryService", true)]
    [InlineData("Game.Core.Services.InventoryService", false)]
    [InlineData("", false)]
    [InlineData("   ", false)]
    [InlineData(null, false)]
    public void Should_EvaluateNewPrefix_WhenCallingIsNew(string? namespaceValue, bool expected)
    {
        var actual = NamespaceConventions.IsNew(namespaceValue!);

        Assert.Equal(expected, actual);
    }
}
