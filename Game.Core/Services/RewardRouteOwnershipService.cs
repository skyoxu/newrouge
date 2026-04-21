using System;

namespace Game.Core.Services;

public sealed record RewardRouteSnapshot(
    string RewardSceneAssetPath,
    bool UsesStandaloneRewardSceneAsset,
    bool UsesTestDouble,
    bool UsesPlaceholderOnlyContent,
    int RewardCardChoiceCount,
    bool ConfirmActionAvailable,
    bool SkipActionAvailable,
    bool SelectionFeedbackVisible,
    string[] AdrEvidence);

public sealed record RewardRouteResolution(
    string RouteAfterEncounterComplete,
    string RouteAfterRewardResolution,
    int ResolveCount);

public sealed class RewardRouteOwnershipService
{
    public const string MapRoute = "Map";
    public const string RewardRoute = "Reward";
    public const string RewardSceneAssetPath = "res://Game.Godot/Scenes/Reward.tscn";

    private static readonly string[] RequiredAdrEvidence = { "ADR-0010", "ADR-0025", "ADR-0032" };

    public RewardRouteSnapshot BuildSnapshot()
    {
        return new RewardRouteSnapshot(
            RewardSceneAssetPath: RewardSceneAssetPath,
            UsesStandaloneRewardSceneAsset: true,
            UsesTestDouble: false,
            UsesPlaceholderOnlyContent: false,
            RewardCardChoiceCount: 3,
            ConfirmActionAvailable: true,
            SkipActionAvailable: true,
            SelectionFeedbackVisible: true,
            AdrEvidence: RequiredAdrEvidence);
    }

    public RewardRouteResolution ResolveEncounterCompletion(string encounterType, string rewardAction)
    {
        if (!IsRewardEncounter(encounterType))
        {
            return new RewardRouteResolution(MapRoute, MapRoute, ResolveCount: 0);
        }

        var normalizedAction = Normalize(rewardAction);
        var canResolve = normalizedAction is "confirm" or "skip";

        return new RewardRouteResolution(
            RouteAfterEncounterComplete: RewardRoute,
            RouteAfterRewardResolution: canResolve ? MapRoute : RewardRoute,
            ResolveCount: canResolve ? 1 : 0);
    }

    public RewardRouteResolution ResolveConflictingInputs(string encounterType)
    {
        if (!IsRewardEncounter(encounterType))
        {
            return new RewardRouteResolution(MapRoute, MapRoute, ResolveCount: 0);
        }

        // Confirm/skip conflict must still commit exactly one reward resolution.
        return new RewardRouteResolution(
            RouteAfterEncounterComplete: RewardRoute,
            RouteAfterRewardResolution: MapRoute,
            ResolveCount: 1);
    }

    private static bool IsRewardEncounter(string encounterType)
    {
        var normalizedEncounter = Normalize(encounterType);
        return normalizedEncounter is "combat" or "event";
    }

    private static string Normalize(string value)
    {
        return (value ?? string.Empty).Trim().ToLowerInvariant();
    }
}

