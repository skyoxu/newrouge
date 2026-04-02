using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.RegularExpressions;
using FluentAssertions;
using Xunit;

namespace Game.Core.Tests.Utilities;

public sealed class ContractsLocationAndDuplicationTests
{
    // RED-FIRST: this should fail until duplicate detection supports class-based DTO declarations.
    // ACC:T7.7
    [Fact]
    public void ShouldFlagDuplicateDtoName_WhenCoreAndGodotContainSameDtoType()
    {
        var fileMap = new Dictionary<string, string>
        {
            ["Game.Core/Contracts/PlayerStateDto.cs"] = "namespace Game.Core.Contracts; public sealed class PlayerStateDto { }",
            ["Game.Godot/Adapters/PlayerStateDto.cs"] = "namespace Game.Godot.Adapters; public sealed class PlayerStateDto { }"
        };

        var duplicateNames = FindDuplicateDtoNames(fileMap);

        duplicateNames.Should().Contain("PlayerStateDto");
    }

    [Fact]
    public void ShouldRejectContractCandidatesOutsideCanonicalDirectory_WhenContractLikeFilesAreScanned()
    {
        var contractCandidatePaths = new[]
        {
            "Game.Core/Contracts/CityDto.cs",
            "Game.Core/Services/CityDto.cs",
            "Game.Godot/Contracts/CityDto.cs"
        };

        var invalidPaths = FindContractCandidatesOutsideCanonicalDirectory(contractCandidatePaths);

        invalidPaths.Should().BeEquivalentTo(
            new[]
            {
                "Game.Core/Services/CityDto.cs",
                "Game.Godot/Contracts/CityDto.cs"
            },
            options => options.WithStrictOrdering());
    }

    [Fact]
    public void ShouldRemainEmpty_WhenGodotLayerDoesNotRedefineCoreContractDtos()
    {
        var fileMap = new Dictionary<string, string>
        {
            ["Game.Core/Contracts/TurnResultDto.cs"] = "namespace Game.Core.Contracts; public record TurnResultDto(int Roll);",
            ["Game.Godot/Adapters/TurnPresenter.cs"] = "namespace Game.Godot.Adapters; public sealed class TurnPresenter { }"
        };

        var duplicateNames = FindDuplicateDtoNames(fileMap);

        duplicateNames.Should().BeEmpty();
    }

    private static IReadOnlyCollection<string> FindContractCandidatesOutsideCanonicalDirectory(IEnumerable<string> filePaths)
    {
        var invalidPaths = filePaths
            .Where(filePath => filePath.EndsWith("Dto.cs", StringComparison.Ordinal))
            .Where(filePath => !filePath.StartsWith("Game.Core/Contracts/", StringComparison.Ordinal))
            .OrderBy(filePath => filePath, StringComparer.Ordinal)
            .ToArray();

        return invalidPaths;
    }

    private static IReadOnlyCollection<string> FindDuplicateDtoNames(IReadOnlyDictionary<string, string> fileMap)
    {
        var declarations = fileMap
            .SelectMany(entry => ExtractDtoTypeNames(entry.Value).Select(typeName => new
            {
                filePath = NormalizePath(entry.Key),
                typeName
            }))
            .Where(item =>
                item.filePath.StartsWith("Game.Core/Contracts/", StringComparison.Ordinal) ||
                item.filePath.StartsWith("Game.Godot/", StringComparison.Ordinal))
            .ToArray();

        var duplicateNames = declarations
            .GroupBy(item => item.typeName, StringComparer.Ordinal)
            .Where(group =>
            {
                var roots = group
                    .Select(item => item.filePath.StartsWith("Game.Core/Contracts/", StringComparison.Ordinal) ? "core" : "godot")
                    .Distinct(StringComparer.Ordinal)
                    .Count();
                return roots > 1;
            })
            .Select(group => group.Key)
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToArray();

        return duplicateNames;
    }

    private static IReadOnlyCollection<string> ExtractDtoTypeNames(string sourceCode)
    {
        var matches = Regex.Matches(
            sourceCode,
            @"\b(?:record|class)\s+(?<name>[A-Za-z_][A-Za-z0-9_]*Dto)\b",
            RegexOptions.CultureInvariant);

        var typeNames = matches
            .Select(match => match.Groups["name"].Value)
            .Distinct(StringComparer.Ordinal)
            .OrderBy(name => name, StringComparer.Ordinal)
            .ToArray();

        return typeNames;
    }

    private static string NormalizePath(string path)
    {
        return path.Replace('\\', '/');
    }
}
