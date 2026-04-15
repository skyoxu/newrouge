using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;

namespace Game.Core.Services;

/// <summary>
/// Deterministic map navigation service for modular Act topology.
/// </summary>
/// <remarks>
/// ADR refs: ADR-0007, ADR-0021.
/// </remarks>
public sealed class MapService
{
    private readonly Dictionary<string, MapNodeDefinition> nodes = new(StringComparer.Ordinal);
    private readonly Dictionary<string, List<string>> outgoingByNode = new(StringComparer.Ordinal);
    private string currentNodeId = string.Empty;
    private string currentState = "MapReady";
    private string nodePreEnterId = string.Empty;

    /// <summary>
    /// Current monotonic state version. Advances only on accepted branch selections.
    /// </summary>
    public int Version { get; private set; }

    public IReadOnlyCollection<string> AllNodeIds => new ReadOnlyCollection<string>(
        nodes.Keys.OrderBy(id => id, StringComparer.Ordinal).ToList());

    public void ConfigureAct(
        string actId,
        IEnumerable<MapNodeDefinition> nodeDefinitions,
        IEnumerable<MapEdgeDefinition> edges,
        string startNodeId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(actId);
        ArgumentNullException.ThrowIfNull(nodeDefinitions);
        ArgumentNullException.ThrowIfNull(edges);
        ArgumentException.ThrowIfNullOrWhiteSpace(startNodeId);

        nodes.Clear();
        outgoingByNode.Clear();

        foreach (var nodeDefinition in nodeDefinitions)
        {
            if (!string.Equals(nodeDefinition.ActId, actId, StringComparison.Ordinal))
            {
                continue;
            }

            nodes[nodeDefinition.NodeId] = nodeDefinition;
            outgoingByNode[nodeDefinition.NodeId] = new List<string>();
        }

        if (!nodes.ContainsKey(startNodeId))
        {
            throw new ArgumentException("Start node must exist in configured act nodes.", nameof(startNodeId));
        }

        foreach (var edge in edges)
        {
            if (!outgoingByNode.ContainsKey(edge.From) || !outgoingByNode.ContainsKey(edge.To))
            {
                continue;
            }

            var outgoing = outgoingByNode[edge.From];
            if (!outgoing.Contains(edge.To, StringComparer.Ordinal))
            {
                outgoing.Add(edge.To);
            }
        }

        currentNodeId = startNodeId;
        currentState = "MapReady";
        nodePreEnterId = string.Empty;
        Version = 0;
    }

    public IReadOnlyList<string> GetOutgoing(string nodeId)
    {
        if (!outgoingByNode.TryGetValue(nodeId, out var outgoing))
        {
            return Array.Empty<string>();
        }

        return outgoing.OrderBy(id => id, StringComparer.Ordinal).ToArray();
    }

    public MapSnapshot GetSnapshot()
    {
        return new MapSnapshot(
            CurrentNodeId: currentNodeId,
            ReachableNodeIds: GetOutgoing(currentNodeId),
            CurrentState: currentState,
            NodePreEnterId: nodePreEnterId,
            Version: Version);
    }

    public BranchSelectionResult SelectBranch(string branchId)
    {
        var reachable = GetOutgoing(currentNodeId);
        if (string.IsNullOrWhiteSpace(branchId) || !reachable.Contains(branchId, StringComparer.Ordinal))
        {
            return BranchSelectionResult.FromRejected("invalid-branch", GetSnapshot());
        }

        var transitions = new List<string>(capacity: 2)
        {
            "MapNodeSelected",
            "MapNodeEntered",
        };

        nodePreEnterId = currentNodeId;
        currentState = "MapNodeSelected";
        currentNodeId = branchId;
        currentState = "MapNodeEntered";
        Version++;

        return BranchSelectionResult.FromAccepted("ok", GetSnapshot(), transitions);
    }
}

public sealed record MapNodeDefinition(string ActId, string NodeId, string NodeType = "combat");

public sealed record MapEdgeDefinition(string From, string To);

public sealed record MapSnapshot(
    string CurrentNodeId,
    IReadOnlyList<string> ReachableNodeIds,
    string CurrentState,
    string NodePreEnterId,
    int Version);

public sealed record BranchSelectionResult(
    bool Accepted,
    string Code,
    MapSnapshot Snapshot,
    IReadOnlyList<string> StateTransitions)
{
    public static BranchSelectionResult FromAccepted(string code, MapSnapshot snapshot, IReadOnlyList<string> transitions)
    {
        return new BranchSelectionResult(true, code, snapshot, transitions);
    }

    public static BranchSelectionResult FromRejected(string code, MapSnapshot snapshot)
    {
        return new BranchSelectionResult(false, code, snapshot, Array.Empty<string>());
    }
}
