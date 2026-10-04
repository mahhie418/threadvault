import pytest

import threadvault.vault.markdown

NAMES = {'UXXX1': 'xxx1', 'CXXX1': 'general'}

TEXTS_CORRESPONDENCE = [
    ('xxx', 'xxx'),
    ('&lt;xxx&gt; &amp;lt;', '<xxx> &lt;'),
    ('<@UXXX1> <@UXXX2|xxx2> <@UXXX3>', '@xxx1 @xxx2 @UXXX3'),
    ('<#CXXX1|xxx> <#CXXX2|xxx2> <#CXXX3>', '#general #xxx2 #CXXX3'),
    ('<!everyone> <!channel> <!here>', '@everyone @channel @here'),
    ('<!subteam^SXXX|@xxx> <!date^1000000000^{date}|xxx>', '@xxx xxx'),
    ('<https://xxx.xxx/?a=1&amp;b=2|xxx>', '[xxx](https://xxx.xxx/?a=1&b=2)'),
    ('<https://xxx.xxx/> <https://xxx.xxx/|https://xxx.xxx/>', '<https://xxx.xxx/> <https://xxx.xxx/>'),
    ('<mailto:xxx@xxx.xxx|xxx@xxx.xxx>', '[xxx@xxx.xxx](mailto:xxx@xxx.xxx)'),
    ('*xxx* *xxx xxx* テスト*テスト*テスト', '**xxx** **xxx xxx** テスト**テスト**テスト'),
    ('1*2*3 * xxx', '1*2*3 * xxx'),
    ('~xxx~ _xxx_', '~~xxx~~ _xxx_'),
    ('`*xxx* &lt;`', '`*xxx* <`'),
    ('xxx```*xxx*\n&lt;xxx&gt;```xxx', 'xxx\n```\n*xxx*\n<xxx>\n```\nxxx'),
    ('&gt; xxx\nxxx', '> xxx\nxxx')
]

@pytest.mark.parametrize(('text', 'expected'), TEXTS_CORRESPONDENCE)
def test_markdown_text_conversion(
    text: str,
    expected: str
) -> None:

    assert threadvault.vault.markdown.convert(text, NAMES) == expected
