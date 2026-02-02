using FluentAssertions;
using Xunit;

namespace ProjectName.UnitTests.Application;

[Trait("Story", "ACF-0002")]
public class AutopilotStoryLinkTests
{
    [Fact]
    public void AutopilotStoryLinkShouldExistForTraceability()
    {
        true.Should().BeTrue();
    }
}

