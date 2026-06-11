// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title Escrow — kupac deponuje ETH, arbiter odobrava isplatu prodavcu.
/// Nema timeout — sredstva ostaju zaključana dok arbiter ne odluči.
contract Escrow {
    address public buyer;
    address public seller;
    address public arbiter;
    uint256 public amount;

    enum State { AWAITING_PAYMENT, AWAITING_DELIVERY, COMPLETE, REFUNDED }
    State public state;

    event FundsDeposited(address indexed buyer, uint256 amount);
    event FundsReleased(address indexed seller, uint256 amount);
    event FundsRefunded(address indexed buyer, uint256 amount);

    modifier onlyArbiter() {
        require(msg.sender == arbiter, "Only arbiter");
        _;
    }

    modifier inState(State expected) {
        require(state == expected, "Invalid state");
        _;
    }

    constructor(address _seller, address _arbiter) {
        buyer   = msg.sender;
        seller  = _seller;
        arbiter = _arbiter;
        state   = State.AWAITING_PAYMENT;
    }

    function deposit() external payable inState(State.AWAITING_PAYMENT) {
        require(msg.sender == buyer, "Only buyer");
        require(msg.value > 0, "Zero amount");
        amount = msg.value;
        state  = State.AWAITING_DELIVERY;
        emit FundsDeposited(buyer, amount);
    }

    function releaseFunds() external onlyArbiter inState(State.AWAITING_DELIVERY) {
        state = State.COMPLETE;
        payable(seller).transfer(amount);
        emit FundsReleased(seller, amount);
    }

    function refund() external onlyArbiter inState(State.AWAITING_DELIVERY) {
        state = State.REFUNDED;
        payable(buyer).transfer(amount);
        emit FundsRefunded(buyer, amount);
    }
}
