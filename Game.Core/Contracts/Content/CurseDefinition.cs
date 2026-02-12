namespace Game.Core.Contracts.Content;

/// <summary>
/// Curse card definition using independent card namespace.
/// </summary>
public sealed record CurseDefinition(
    string CardId,
    string NameKey,
    string DescriptionKey,
    bool Removable
);

