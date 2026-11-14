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
