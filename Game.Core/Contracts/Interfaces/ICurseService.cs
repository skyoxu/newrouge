using Game.Core.Contracts.Content;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Curse add/remove service.
/// </summary>
public interface ICurseService
{
    CurseDefinition AddCurse(string cardId);
    bool RemoveCurse(string cardId);
}

