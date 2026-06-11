// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title DAOVoting — jednostavno DAO glasanje: predlog, glasanje, izvršavanje.
contract DAOVoting {
    address public admin;
    uint256 public votingDuration = 3 days;
    uint256 public quorum = 3;

    struct Proposal {
        string  description;
        address target;
        bytes   callData;
        uint256 voteEnd;
        uint256 votesFor;
        uint256 votesAgainst;
        bool    executed;
    }

    mapping(uint256 => Proposal)         public proposals;
    mapping(uint256 => mapping(address => bool)) public hasVoted;
    uint256 public proposalCount;

    event ProposalCreated(uint256 indexed id, string description);
    event Voted(uint256 indexed id, address voter, bool support);
    event ProposalExecuted(uint256 indexed id, bool passed);

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    constructor() {
        admin = msg.sender;
    }

    function createProposal(string calldata desc, address target, bytes calldata data)
        external onlyAdmin returns (uint256)
    {
        uint256 id = proposalCount++;
        proposals[id] = Proposal(desc, target, data, block.timestamp + votingDuration, 0, 0, false);
        emit ProposalCreated(id, desc);
        return id;
    }

    function vote(uint256 id, bool support) external {
        Proposal storage p = proposals[id];
        require(block.timestamp < p.voteEnd, "Voting ended");
        require(!hasVoted[id][msg.sender], "Already voted");
        hasVoted[id][msg.sender] = true;
        support ? p.votesFor++ : p.votesAgainst++;
        emit Voted(id, msg.sender, support);
    }

    function execute(uint256 id) external {
        Proposal storage p = proposals[id];
        require(block.timestamp >= p.voteEnd, "Voting ongoing");
        require(!p.executed, "Already executed");
        bool passed = p.votesFor > p.votesAgainst && p.votesFor >= quorum;
        p.executed = true;
        if (passed) {
            (bool ok,) = p.target.call(p.callData);
            require(ok, "Execution failed");
        }
        emit ProposalExecuted(id, passed);
    }

    function setQuorum(uint256 newQuorum) external onlyAdmin {
        quorum = newQuorum;
    }
}
