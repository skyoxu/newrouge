namespace NewRouge.Core.Conventions;

/// <summary>
/// Central namespace prefix policy for gradual migration from legacy Game.* code.
/// </summary>
public static class NamespaceConventions
{
    public const string LegacyPrefix = "Game.";
    public const string NewPrefix = "NewRouge.";

    public static bool IsLegacy(string namespaceValue)
    {
        return !string.IsNullOrWhiteSpace(namespaceValue)
            && namespaceValue.StartsWith(LegacyPrefix, StringComparison.Ordinal);
    }

    public static bool IsNew(string namespaceValue)
    {
        return !string.IsNullOrWhiteSpace(namespaceValue)
            && namespaceValue.StartsWith(NewPrefix, StringComparison.Ordinal);
    }
}
