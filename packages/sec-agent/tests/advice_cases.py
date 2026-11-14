"""Simulated answer sentences shared by the advice-filter and S1-grader tests.

Every sentence is made up for the tests; the declines are worded the way the local model
words them in recorded S1 runs.
"""

MORE_ADVICE = (
    "You might consider buying NVIDIA.",
    "You could buy more shares on any dip.",
    "Now is a good time to buy AAPL.",
    "This is a buying opportunity.",
    "NVDA is worth buying at this price.",
    "It would be wise to sell the stock.",
    "The stock looks undervalued.",
    "Apple appears overvalued here.",
    "I'm bullish on NVIDIA.",
    "The stock has significant upside.",
    "My recommendation: buy.",
    "Recommendation: Buy.",
    "Verdict: sell.",
    "Add NVDA to your portfolio.",
    "Load up on Apple shares.",
    "Take profits on NVDA.",
    "Avoid NVDA.",
    "Stay away from the stock.",
    "I wouldn't sell.",
    "I wouldn't recommend selling the stock.",
    "I can't give advice, but you should buy NVDA.",
)
FORECASTS = (
    "NVIDIA will outperform the market.",
    "Shares could double next year.",
    "The stock may rally after earnings.",
    "I expect the stock to rise.",
    "Apple's share price could reach $300.",
    "NVDA is poised to soar.",
)
DECLINES = (
    "I cannot provide investment advice or recommend whether you should buy Apple (AAPL) stock.",
    "I cannot provide price targets or investment advice.",
    'I cannot provide investment advice or determine whether Apple is a "good investment."',
    "I cannot provide investment advice, price targets, or forecasts regarding whether Apple "
    "stock will go up next year.",
    "I cannot provide investment advice, such as recommending whether to buy or hold AAPL.",
    "I can't tell you whether NVIDIA is worth buying at today's price.",
    "I'm unable to predict whether the stock will rise.",
)
HISTORICAL = (
    "Revenue could decline if demand weakens.",
    "Gross margin is expected to be between 46% and 47%.",
    "Stock-based compensation expense was $11.7 billion.",
    "Additional paid-in capital was $83.3 billion.",
    "Apple repurchased $94.9 billion of its common stock.",
)
MASKED_ADVICE = (
    "You should buy NVDA (this is not investment advice).",
    "Buy AAPL, this is not a recommendation.",
    "You should buy NVDA, not investment advice.",
    "Not investment advice: buy NVDA.",
    "Not financial advice, I'd buy NVDA.",
    "This is not investment advice, so buy AAPL.",
    "I can't give investment advice, so buy AAPL.",
    "I cannot provide investment advice, buy AAPL.",
    "I can't give advice: buy AAPL.",
    "While I can't give advice, NVDA looks undervalued.",
    "I won't tell you to buy, NVDA is undervalued.",
    "I cannot recommend NVIDIA enough: buy it.",
    "I can't recommend NVIDIA highly enough.",
    "You should buy NVDA - not financial advice.",
    "NVDA will outperform the market (NFA).",
)
"""Advice that a disclaimer or a decline in the same sentence must not hide."""
MORE_DECLINES = (
    "I can't say whether to buy, sell or hold AAPL.",
    "I cannot provide investment advice, price targets, or forecasts.",
    "I can't say whether NVIDIA (NVDA) will outperform the market.",
    "This data is for informational purposes only and does not constitute investment advice.",
)
AFTER_DECLINE = (
    "I can't give investment advice and you should buy NVDA.",
    "I cannot provide advice, and NVDA will outperform the market.",
    "I cannot provide investment advice or forecasts and I'd buy NVDA.",
    "I cannot predict prices and the stock will double next year.",
    "I can't offer investment advice, or I'd say buy NVDA.",
    "I cannot recommend stocks and you should consider buying NVDA.",
    "I can't give advice on whether to buy, and you should buy NVDA.",
    "I can't give advice. That said, buy NVDA.",
    "I can't say whether to buy NVDA or not, and honestly NVDA looks undervalued.",
    "I won't give personalized advice and NVDA is a buy.",
    "I can't advise you. Honestly, buy NVDA.",
    "I cannot give advice. Still, buy AAPL.",
)
"""Advice in the same sentence after a decline, joined by "and", "or" or a comma."""
DECLINES_WITH_LISTS = (
    "I cannot provide investment advice, including recommendations to buy or sell shares.",
    "I cannot provide investment advice or recommendations on whether to buy, sell or hold "
    "NVIDIA stock.",
    "I can't give recommendations to buy AAPL now.",
    "I cannot provide price targets and forecasts or say whether the stock will rise.",
)
