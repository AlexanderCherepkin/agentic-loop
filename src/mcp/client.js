'use strict';

/**
 * MCP Client Manager — unified interface to all MCP servers.
 *
 * Supports both TypeScript (@modelcontextprotocol/sdk) and Python (JSON-RPC)
 * servers over stdio transport.
 */

const fs = require('fs');
const path = require('path');
const { Client } = require('@modelcontextprotocol/sdk/client/index.js');
const { StdioClientTransport } = require('@modelcontextprotocol/sdk/client/stdio.js');

const DEFAULT_CONFIG_PATH = path.join(__dirname, '..', '..', 'mcp-config.json');

class MCPClientManager {
  constructor(configPath = DEFAULT_CONFIG_PATH) {
    this.configPath = configPath;
    this.config = this._loadConfig();
    this.clients = new Map();
    this.tools = new Map();
    this.connected = false;
  }

  _loadConfig() {
    if (!fs.existsSync(this.configPath)) {
      return { mcpServers: {} };
    }
    return JSON.parse(fs.readFileSync(this.configPath, 'utf8'));
  }

  /**
   * Connect to all configured MCP servers.
   * @returns {Promise<Array<{name: string, ok: boolean, error?: string, tools: number}>>}
   */
  async connectAll() {
    const results = [];
    for (const [name, serverCfg] of Object.entries(this.config.mcpServers || {})) {
      try {
        const result = await this._connectOne(name, serverCfg);
        results.push(result);
      } catch (err) {
        results.push({ name, ok: false, error: err.message, tools: 0 });
      }
    }
    this.connected = results.some((r) => r.ok);
    return results;
  }

  async _connectOne(name, serverCfg) {
    const transport = new StdioClientTransport({
      command: serverCfg.command,
      args: serverCfg.args || [],
      env: { ...process.env, ...(serverCfg.env || {}) },
    });

    const client = new Client({ name: `agentic-loop-${name}`, version: '1.0.0' });
    await client.connect(transport);
    this.clients.set(name, { client, transport });

    const toolsResp = await client.listTools();
    const tools = toolsResp.tools || [];
    this.tools.set(name, tools);

    return { name, ok: true, tools: tools.length };
  }

  /**
   * Call a tool on a specific server.
   * @param {string} serverName
   * @param {string} toolName
   * @param {object} args
   */
  async callTool(serverName, toolName, args) {
    const entry = this.clients.get(serverName);
    if (!entry) {
      throw new Error(`Server not connected: ${serverName}`);
    }
    return await entry.client.callTool({ name: toolName, arguments: args });
  }

  /**
   * Get all tools from all connected servers.
   */
  getAllTools() {
    const all = [];
    for (const [serverName, tools] of this.tools) {
      for (const tool of tools) {
        all.push({ server: serverName, name: tool.name, description: tool.description });
      }
    }
    return all;
  }

  /**
   * Disconnect all servers.
   */
  async disconnectAll() {
    for (const [name, entry] of this.clients) {
      try {
        await entry.transport.close();
      } catch {
        // ignore
      }
    }
    this.clients.clear();
    this.tools.clear();
    this.connected = false;
  }
}

module.exports = { MCPClientManager };
