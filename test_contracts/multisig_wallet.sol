// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title MultisigWallet — 2-of-3 multisig novčanik. Transakcija zahteva 2 potvrde od 3 ownera.
contract MultisigWallet {
    address[3] public owners;
    uint256    public required = 2;

    struct Transaction {
        address to;
        uint256 value;
        bytes   data;
        bool    executed;
        uint256 confirmations;
    }

    Transaction[] public transactions;
    mapping(uint256 => mapping(address => bool)) public confirmed;

    event Deposit(address indexed sender, uint256 amount);
    event TxSubmitted(uint256 indexed txId, address indexed to, uint256 value);
    event TxConfirmed(uint256 indexed txId, address indexed owner);
    event TxExecuted(uint256 indexed txId);

    modifier onlyOwner() {
        bool found;
        for (uint256 i; i < 3; i++) {
            if (owners[i] == msg.sender) { found = true; break; }
        }
        require(found, "Not owner");
        _;
    }

    constructor(address[3] memory _owners) {
        owners = _owners;
    }

    receive() external payable {
        emit Deposit(msg.sender, msg.value);
    }

    function submitTransaction(address to, uint256 value, bytes calldata data)
        external onlyOwner returns (uint256)
    {
        uint256 txId = transactions.length;
        transactions.push(Transaction(to, value, data, false, 0));
        emit TxSubmitted(txId, to, value);
        return txId;
    }

    function confirmTransaction(uint256 txId) external onlyOwner {
        require(!confirmed[txId][msg.sender], "Already confirmed");
        confirmed[txId][msg.sender] = true;
        transactions[txId].confirmations++;
        emit TxConfirmed(txId, msg.sender);
    }

    function executeTransaction(uint256 txId) external onlyOwner {
        Transaction storage tx_ = transactions[txId];
        require(!tx_.executed, "Already executed");
        require(tx_.confirmations >= required, "Not enough confirmations");
        tx_.executed = true;
        (bool ok,) = tx_.to.call{value: tx_.value}(tx_.data);
        require(ok, "Execution failed");
        emit TxExecuted(txId);
    }
}
