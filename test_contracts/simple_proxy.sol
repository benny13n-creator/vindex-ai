// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title SimpleProxy — minimalni upgradeable proxy sa delegatecall i upgradeTo.
/// Admin može promeniti implementaciju u bilo kom trenutku bez vremenskog ograničenja.
contract SimpleProxy {
    address public implementation;
    address public admin;

    event Upgraded(address indexed newImplementation);
    event AdminChanged(address indexed newAdmin);

    constructor(address _implementation) {
        admin          = msg.sender;
        implementation = _implementation;
    }

    modifier onlyAdmin() {
        require(msg.sender == admin, "Not admin");
        _;
    }

    function upgradeTo(address newImplementation) external onlyAdmin {
        require(newImplementation != address(0), "Zero address");
        implementation = newImplementation;
        emit Upgraded(newImplementation);
    }

    function changeAdmin(address newAdmin) external onlyAdmin {
        require(newAdmin != address(0), "Zero address");
        admin = newAdmin;
        emit AdminChanged(newAdmin);
    }

    fallback() external payable {
        address impl = implementation;
        require(impl != address(0), "No implementation");
        assembly {
            calldatacopy(0, 0, calldatasize())
            let result := delegatecall(gas(), impl, 0, calldatasize(), 0, 0)
            returndatacopy(0, 0, returndatasize())
            switch result
            case 0 { revert(0, returndatasize()) }
            default { return(0, returndatasize()) }
        }
    }

    receive() external payable {}
}
