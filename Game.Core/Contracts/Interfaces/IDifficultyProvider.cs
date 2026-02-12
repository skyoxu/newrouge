using Game.Core.Contracts.Config;

namespace Game.Core.Contracts.Interfaces;

/// <summary>
/// Difficulty config provider.
/// </summary>
public interface IDifficultyProvider
{
    DifficultyConfig GetById(int difficultyId);
}

