namespace Game.Core.Contracts.Guild;

/// <summary>
/// Domain event: core.guild.member.joined
/// Description: Emitted when a user joins a guild.
/// </summary>
/// <remarks>
/// Follows ADR-0004 event contracts for the guild domain.
/// </remarks>
public sealed record GuildMemberJoined(
    string UserId,
    string GuildId,
    System.DateTimeOffset JoinedAt,
    string Role // member | admin
)
{
    public const string EventType = EventTypes.GuildMemberJoined;
}

