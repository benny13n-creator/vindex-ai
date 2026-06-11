// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title TokenVesting — linearna vest sa cliff periodom. Beneficiary prima tokene,
/// owner može opozvati vest pre isteka (revoke). Nema emergency withdraw za beneficijara.
contract TokenVesting {
    address public owner;
    address public beneficiary;
    uint256 public startTime;
    uint256 public cliffDuration  = 180 days;
    uint256 public vestingDuration = 730 days; // 2 godine
    uint256 public totalAmount;
    uint256 public releasedAmount;
    bool    public revoked;

    event TokensReleased(address beneficiary, uint256 amount);
    event VestingRevoked(uint256 amountReturned);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor(address _beneficiary, uint256 _totalAmount) payable {
        require(msg.value == _totalAmount, "Amount mismatch");
        owner       = msg.sender;
        beneficiary = _beneficiary;
        totalAmount = _totalAmount;
        startTime   = block.timestamp;
    }

    function release() external {
        require(!revoked, "Vesting revoked");
        require(block.timestamp >= startTime + cliffDuration, "Cliff period active");
        uint256 vested   = _vestedAmount();
        uint256 releasable = vested - releasedAmount;
        require(releasable > 0, "No tokens due");
        releasedAmount += releasable;
        payable(beneficiary).transfer(releasable);
        emit TokensReleased(beneficiary, releasable);
    }

    function revoke() external onlyOwner {
        require(!revoked, "Already revoked");
        revoked = true;
        uint256 vested    = _vestedAmount();
        uint256 returnAmt = totalAmount - vested;
        payable(owner).transfer(returnAmt);
        emit VestingRevoked(returnAmt);
    }

    function _vestedAmount() internal view returns (uint256) {
        if (block.timestamp < startTime + cliffDuration) return 0;
        if (block.timestamp >= startTime + vestingDuration) return totalAmount;
        uint256 elapsed = block.timestamp - startTime;
        return (totalAmount * elapsed) / vestingDuration;
    }
}
