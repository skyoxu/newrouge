namespace Game.Core.Services;

public enum MapNodeRouteDestination
{
    Map,
    Combat,
    Event,
    Shop,
    Rest,
}

public sealed record MapNodeRouteProgress(
    MapNodeRouteDestination CurrentState,
    int CompletedNodeCount);

public sealed record MapNodeRouteRequest(
    string NodeId,
    string NodeType,
    bool IsReachable,
    string? BlockReason = null);

public sealed record MapNodeRouteResult(
    bool IsSuccess,
    MapNodeRouteDestination Destination,
    MapNodeRouteProgress NewProgress,
    string BlockReason = "");

public sealed class MapNodeRouteOwnershipService
{
    public MapNodeRouteResult StartRoute(MapNodeRouteRequest request, MapNodeRouteProgress progress)
    {
        ArgumentNullException.ThrowIfNull(request);
        ArgumentNullException.ThrowIfNull(progress);

        if (progress.CurrentState != MapNodeRouteDestination.Map)
        {
            return new MapNodeRouteResult(false, progress.CurrentState, progress, "route-owner-mismatch");
        }

        if (!request.IsReachable)
        {
            var reason = string.IsNullOrWhiteSpace(request.BlockReason)
                ? "Node is unreachable."
                : request.BlockReason!.Trim();
            return new MapNodeRouteResult(false, progress.CurrentState, progress, reason);
        }

        if (!TryResolveDestination(request.NodeType, out var destination))
        {
            return new MapNodeRouteResult(false, progress.CurrentState, progress, "unsupported-node-type");
        }

        var advanced = progress with { CurrentState = destination };
        return new MapNodeRouteResult(true, destination, advanced);
    }

    public MapNodeRouteResult CompleteRoute(MapNodeRouteProgress progress)
    {
        ArgumentNullException.ThrowIfNull(progress);

        var isNodeFlow = progress.CurrentState is MapNodeRouteDestination.Combat
            or MapNodeRouteDestination.Event
            or MapNodeRouteDestination.Shop
            or MapNodeRouteDestination.Rest;

        if (!isNodeFlow)
        {
            return new MapNodeRouteResult(false, progress.CurrentState, progress, "no-node-flow-in-progress");
        }

        var returned = progress with
        {
            CurrentState = MapNodeRouteDestination.Map,
            CompletedNodeCount = progress.CompletedNodeCount + 1,
        };
        return new MapNodeRouteResult(true, MapNodeRouteDestination.Map, returned);
    }

    public bool TryResolveDestination(string nodeType, out MapNodeRouteDestination destination)
    {
        var normalized = (nodeType ?? string.Empty).Trim().ToLowerInvariant();
        destination = normalized switch
        {
            "combat" => MapNodeRouteDestination.Combat,
            "event" => MapNodeRouteDestination.Event,
            "shop" => MapNodeRouteDestination.Shop,
            "rest" => MapNodeRouteDestination.Rest,
            _ => MapNodeRouteDestination.Map,
        };
        return destination != MapNodeRouteDestination.Map;
    }
}
