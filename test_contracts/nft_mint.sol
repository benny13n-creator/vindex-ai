// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title NFTMint — ERC-721 style NFT sa max supply, javnim mintom i owner withdraw.
contract NFTMint {
    string  public name     = "VindexNFT";
    string  public symbol   = "VNFT";
    address public owner;
    uint256 public maxSupply = 1000;
    uint256 public mintPrice = 0.05 ether;
    uint256 public totalMinted;

    mapping(uint256 => address)  public ownerOf;
    mapping(address => uint256)  public balanceOf;
    mapping(uint256 => address)  public approved;
    mapping(uint256 => string)   public tokenURI;

    event Transfer(address indexed from, address indexed to, uint256 indexed tokenId);
    event Approval(address indexed owner, address indexed approved, uint256 indexed tokenId);
    event MintPriceUpdated(uint256 newPrice);

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function mint(string calldata uri) external payable returns (uint256) {
        require(totalMinted < maxSupply, "Max supply reached");
        require(msg.value >= mintPrice, "Insufficient payment");
        uint256 tokenId = ++totalMinted;
        ownerOf[tokenId]  = msg.sender;
        tokenURI[tokenId] = uri;
        balanceOf[msg.sender]++;
        emit Transfer(address(0), msg.sender, tokenId);
        return tokenId;
    }

    function transfer(address to, uint256 tokenId) external {
        require(ownerOf[tokenId] == msg.sender || approved[tokenId] == msg.sender, "Not authorized");
        address from = ownerOf[tokenId];
        ownerOf[tokenId] = to;
        balanceOf[from]--;
        balanceOf[to]++;
        approved[tokenId] = address(0);
        emit Transfer(from, to, tokenId);
    }

    function setMintPrice(uint256 newPrice) external onlyOwner {
        mintPrice = newPrice;
        emit MintPriceUpdated(newPrice);
    }

    function withdrawFunds() external onlyOwner {
        payable(owner).transfer(address(this).balance);
    }
}
