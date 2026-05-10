const { Telegraf, session } = require('telegraf');
const { message } = require('telegraf/filters');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const { exec } = require('child_process');
const util = require('util');
const { Client } = require('ssh2');
const FormData = require('form-data');
require('dotenv').config();

const execPromise = util.promisify(exec);

// ========== Configuration ==========
const BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN;
const ADMIN_ID = parseInt(process.env.TELEGRAM_ADMIN_ID);

const bot = new Telegraf(BOT_TOKEN);
bot.use(session());

// ========== GitHub Configuration ==========
const GITHUB_CONFIG = {
    token: process.env.GITHUB_TOKEN,
    repo: process.env.GITHUB_REPO,
    branch: process.env.GITHUB_BRANCH,
    owner: process.env.GITHUB_OWNER
};

// ========== Firebase Configuration ==========
const FIREBASE_CONFIG = {
    apiKey: process.env.FIREBASE_API_KEY,
    authDomain: process.env.FIREBASE_AUTH_DOMAIN,
    databaseURL: process.env.FIREBASE_DATABASE_URL,
    projectId: process.env.FIREBASE_PROJECT_ID,
    storageBucket: process.env.FIREBASE_STORAGE_BUCKET
};

// ========== Render Configuration ==========
const RENDER_CONFIG = {
    apiKey: process.env.RENDER_API_KEY,
    serviceId: process.env.RENDER_SERVICE_ID,
    url: process.env.RENDER_URL
};

// ========== KataBump Configuration ==========
const KATABUMP_CONFIG = {
    sftp_host: process.env.KATABUMP_SFTP_HOST,
    sftp_port: parseInt(process.env.KATABUMP_SFTP_PORT),
    sftp_user: process.env.KATABUMP_SFTP_USER,
    sftp_password: process.env.KATABUMP_SFTP_PASSWORD,
    web_url: process.env.KATABUMP_WEB_URL,
    server_id: process.env.KATABUMP_SERVER_ID
};

// ========== Helper Functions ==========
async function callRenderAPI(endpoint, method = 'GET', body = null) {
    try {
        const options = {
            method,
            headers: {
                'Authorization': `Bearer ${RENDER_CONFIG.apiKey}`,
                'Accept': 'application/json'
            }
        };
        if (body) {
            options.headers['Content-Type'] = 'application/json';
            options.body = JSON.stringify(body);
        }
        const response = await fetch(`https://api.render.com/v1${endpoint}`, options);
        return await response.json();
    } catch (error) {
        console.error('Render API Error:', error);
        return { error: error.message };
    }
}

async function uploadToKataBump(content, remotePath) {
    return new Promise((resolve, reject) => {
        const conn = new Client();
        
        conn.on('ready', () => {
            conn.sftp((err, sftp) => {
                if (err) {
                    reject(err);
                    return;
                }
                
                sftp.writeFile(`/home/container/${remotePath}`, content, (err) => {
                    if (err) reject(err);
                    else resolve(true);
                    conn.end();
                });
            });
        }).on('error', (err) => {
            reject(err);
        }).connect({
            host: KATABUMP_CONFIG.sftp_host,
            port: KATABUMP_CONFIG.sftp_port,
            username: KATABUMP_CONFIG.sftp_user,
            password: KATABUMP_CONFIG.sftp_password
        });
    });
}

async function executeSSHCommand(command) {
    return new Promise((resolve, reject) => {
        const conn = new Client();
        
        conn.on('ready', () => {
            conn.exec(command, (err, stream) => {
                if (err) {
                    reject(err);
                    return;
                }
                
                let output = '';
                stream.on('data', (data) => { output += data.toString(); });
                stream.on('close', () => {
                    resolve(output);
                    conn.end();
                });
            });
        }).on('error', reject).connect({
            host: KATABUMP_CONFIG.sftp_host,
            port: KATABUMP_CONFIG.sftp_port,
            username: KATABUMP_CONFIG.sftp_user,
            password: KATABUMP_CONFIG.sftp_password
        });
    });
}

async function getFileFromGitHub(filePath) {
    try {
        const url = `https://api.github.com/repos/${GITHUB_CONFIG.owner}/${GITHUB_CONFIG.repo}/contents/${filePath}`;
        const response = await fetch(url, {
            headers: {
                'Authorization': `token ${GITHUB_CONFIG.token}`,
                'Accept': 'application/vnd.github.v3.raw'
            }
        });
        if (!response.ok) return null;
        return await response.text();
    } catch (error) {
        console.error(`GitHub get error: ${error.message}`);
        return null;
    }
}

async function uploadToGitHub(filePath, content, commitMessage) {
    try {
        const encoded = Buffer.from(content).toString('base64');
        const url = `https://api.github.com/repos/${GITHUB_CONFIG.owner}/${GITHUB_CONFIG.repo}/contents/${filePath}`;
        
        let sha = null;
        try {
            const checkResponse = await fetch(url, {
                headers: { 'Authorization': `token ${GITHUB_CONFIG.token}` }
            });
            if (checkResponse.ok) {
                const data = await checkResponse.json();
                sha = data.sha;
            }
        } catch (e) {}
        
        const payload = {
            message: commitMessage,
            content: encoded,
            branch: GITHUB_CONFIG.branch
        };
        if (sha) payload.sha = sha;
        
        const response = await fetch(url, {
            method: 'PUT',
            headers: {
                'Authorization': `token ${GITHUB_CONFIG.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        return response.ok;
    } catch (error) {
        console.error(`GitHub upload error: ${error.message}`);
        return false;
    }
}

async function deleteFromGitHub(filePath, commitMessage) {
    try {
        const url = `https://api.github.com/repos/${GITHUB_CONFIG.owner}/${GITHUB_CONFIG.repo}/contents/${filePath}`;
        const checkResponse = await fetch(url, {
            headers: { 'Authorization': `token ${GITHUB_CONFIG.token}` }
        });
        
        if (!checkResponse.ok) return false;
        
        const data = await checkResponse.json();
        const payload = {
            message: commitMessage,
            sha: data.sha,
            branch: GITHUB_CONFIG.branch
        };
        
        const response = await fetch(url, {
            method: 'DELETE',
            headers: {
                'Authorization': `token ${GITHUB_CONFIG.token}`,
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        return response.ok;
    } catch (error) {
        console.error(`GitHub delete error: ${error.message}`);
        return false;
    }
}

async function triggerRenderDeploy() {
    try {
        const response = await fetch(
            `https://api.render.com/v1/services/${RENDER_CONFIG.serviceId}/deploys`,
            {
                method: 'POST',
                headers: { 'Authorization': `Bearer ${RENDER_CONFIG.apiKey}` }
            }
        );
        return response.status === 201;
    } catch (error) {
        console.error(`Render deploy error: ${error.message}`);
        return false;
    }
}

// ========== HTML Page Generator ==========
function generatePageHTML(pageId, title, description, icon, iconColor, content, jsFunctions = '') {
    return `<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>${title}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
    <style>
        * { font-family: 'Cairo', sans-serif; }
        body { background: #f0f2f5; }
        .card-hover { transition: all 0.2s; }
        .card-hover:hover { transform: translateY(-4px); box-shadow: 0 10px 25px -5px rgba(0,0,0,0.1); }
    </style>
</head>
<body>
    <div class="max-w-md mx-auto p-4">
        <div class="bg-white rounded-2xl shadow-lg p-6">
            <div class="text-center mb-6">
                <i class="fa-solid ${icon} text-4xl ${iconColor}"></i>
                <h1 class="text-2xl font-bold mt-2">${title}</h1>
                <p class="text-slate-500">${description}</p>
            </div>
            <div id="pageContent">
                ${content}
            </div>
        </div>
        <div class="mt-4 text-center">
            <a href="/" class="text-teal-600 text-sm">← Back to Home</a>
        </div>
    </div>
    <script>
        const API_URL = window.location.origin;
        const PAGE_ID = '${pageId}';
        
        ${jsFunctions}
        
        if (typeof loadPageData === 'function') loadPageData();
    </script>
</body>
</html>`;
}

// ========== Bot Commands ==========

// Start command
bot.start(async (ctx) => {
    const userId = ctx.from.id;
    
    if (userId !== ADMIN_ID) {
        await ctx.reply('❌ Unauthorized access to this bot');
        return;
    }
    
    await ctx.reply(`
👑 **All Arab Services Admin Bot v3.0**

━━━━━━━━━━━━━━━━━━━━
📋 **Page Management**
━━━━━━━━━━━━━━━━━━━━
/create_page <id> <title> <desc> <icon> <color> [content]
/delete_page <id>
/list_pages

━━━━━━━━━━━━━━━━━━━━
🔘 **Button Management**
━━━━━━━━━━━━━━━━━━━━
/add_home_button <title> <url> <icon> <color>
/add_page_button <page> <id> <text> <icon> <color> <action>

━━━━━━━━━━━━━━━━━━━━
📦 **Service Management**
━━━━━━━━━━━━━━━━━━━━
/add_service - Interactive
/list_services
/delete_service <id>
/approve_service <id>
/reject_service <id> [reason]

━━━━━━━━━━━━━━━━━━━━
👥 **User Management**
━━━━━━━━━━━━━━━━━━━━
/add_points <id> <amount>
/remove_points <id> <amount>
/view_users
/find_user <id>
/give_admin <id>

━━━━━━━━━━━━━━━━━━━━
🚀 **Deployment**
━━━━━━━━━━━━━━━━━━━━
/deploy - Deploy to Render
/deploy_katabump - Deploy to KataBump
/sync_all - Sync all platforms

━━━━━━━━━━━━━━━━━━━━
📊 **System**
━━━━━━━━━━━━━━━━━━━━
/stats - System statistics
/backup - Create backup
/status - Service status

━━━━━━━━━━━━━━━━━━━━
🌐 **App URL:** ${RENDER_CONFIG.url}
    `);
});

// Create page command
bot.command('create_page', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const text = ctx.message.text.replace('/create_page', '').trim();
    const parts = text.split(' ');
    
    if (parts.length < 5) {
        await ctx.reply('⚠️ **Usage:** `/create_page <id> <title> <description> <icon> <color> [content]`\n\n📝 Example: `/create_page transfer Transfer_Points Transfer_your_points fa-exchange-alt green`');
        return;
    }
    
    const pageId = parts[0];
    const title = parts[1];
    const description = parts[2];
    const icon = parts[3];
    const color = parts[4];
    const content = parts.slice(5).join(' ') || '<p class="text-center text-slate-500">Page content goes here...</p>';
    
    await ctx.reply(`📄 **Creating page \`${pageId}\`...**`);
    
    const jsFunctions = `
async function loadPageData() {
    try {
        const response = await fetch(\`\${API_URL}/api/page-data/${pageId}\`);
        const data = await response.json();
        if (data.success) {
            document.getElementById('pageContent').innerHTML = data.html;
        }
    } catch(e) { console.error(e); }
}
`;
    
    const html = generatePageHTML(pageId, title, description, icon, `text-${color}-500`, content, jsFunctions);
    const jsFile = `// ${pageId}.js - Created by bot
const API_URL = window.location.origin;

console.log('✅ ${pageId}.js loaded');
`;
    
    const htmlUploaded = await uploadToGitHub(`public/${pageId}.html`, html, `Create page: ${pageId}`);
    const jsUploaded = await uploadToGitHub(`public/${pageId}.js`, jsFile, `Create JS: ${pageId}`);
    
    if (htmlUploaded && jsUploaded) {
        await triggerRenderDeploy();
        await ctx.reply(`
✅ **Page created successfully!**

🌐 **URL:** ${RENDER_CONFIG.url}/${pageId}.html
📁 **Files:**
- \`public/${pageId}.html\`
- \`public/${pageId}.js\`

💡 To add buttons:
\`/add_page_button ${pageId} button_id text fa-icon color action\`
        `);
    } else {
        await ctx.reply('❌ Failed to create page');
    }
});

// Delete page command
bot.command('delete_page', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const pageId = ctx.message.text.replace('/delete_page', '').trim();
    if (!pageId) {
        await ctx.reply('⚠️ **Usage:** `/delete_page <page_id>`');
        return;
    }
    
    await ctx.reply(`🗑️ **Deleting page \`${pageId}\`...**`);
    
    const deletedHtml = await deleteFromGitHub(`public/${pageId}.html`, `Delete page: ${pageId}`);
    const deletedJs = await deleteFromGitHub(`public/${pageId}.js`, `Delete JS: ${pageId}`);
    
    if (deletedHtml || deletedJs) {
        await triggerRenderDeploy();
        await ctx.reply(`✅ **Page \`${pageId}\` deleted**`);
    } else {
        await ctx.reply(`❌ Failed to delete page`);
    }
});

// List pages command
bot.command('list_pages', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    try {
        const url = `https://api.github.com/repos/${GITHUB_CONFIG.owner}/${GITHUB_CONFIG.repo}/contents/public`;
        const response = await fetch(url, {
            headers: { 'Authorization': `token ${GITHUB_CONFIG.token}` }
        });
        
        if (response.ok) {
            const files = await response.json();
            const htmlFiles = files.filter(f => f.name.endsWith('.html'));
            
            if (htmlFiles.length > 0) {
                let text = '📄 **Available Pages**\n\n';
                for (const file of htmlFiles) {
                    const pageName = file.name.replace('.html', '');
                    text += `🔗 [${pageName}](${RENDER_CONFIG.url}/${file.name})\n`;
                }
                await ctx.reply(text);
            } else {
                await ctx.reply('📄 **No custom pages found**');
            }
        } else {
            await ctx.reply('❌ Failed to fetch pages');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Add home button command
bot.command('add_home_button', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const text = ctx.message.text.replace('/add_home_button', '').trim();
    const parts = text.split(' ');
    
    if (parts.length < 4) {
        await ctx.reply('⚠️ **Usage:** `/add_home_button <title> <url> <icon> <color>`\n\n📝 Example: `/add_home_button Transfer /transfer.html fa-exchange-alt green`');
        return;
    }
    
    const title = parts[0];
    const url = parts[1];
    const icon = parts[2];
    const color = parts[3];
    
    let indexHtml = await getFileFromGitHub('index.html');
    if (!indexHtml) {
        await ctx.reply('❌ Failed to fetch homepage');
        return;
    }
    
    const newButton = `<a href="${url}" class="bg-white p-3 rounded-xl shadow text-center hover:shadow-md transition"><i class="fa-solid ${icon} text-xl text-${color}-600 mb-1"></i><p class="text-xs font-bold">${title}</p></a>`;
    
    if (indexHtml.includes('<div class="grid grid-cols-4 gap-3">')) {
        const newHtml = indexHtml.replace(
            '<div class="grid grid-cols-4 gap-3">',
            `<div class="grid grid-cols-4 gap-3">\n                ${newButton}`
        );
        
        if (await uploadToGitHub('index.html', newHtml, `Add home button: ${title}`)) {
            await triggerRenderDeploy();
            await ctx.reply(`✅ **Button \`${title}\` added to homepage**\n🔗 ${RENDER_CONFIG.url}${url}`);
        } else {
            await ctx.reply('❌ Failed to add button');
        }
    } else {
        await ctx.reply('❌ Could not find button container in homepage');
    }
});

// Add page button command
bot.command('add_page_button', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const text = ctx.message.text.replace('/add_page_button', '').trim();
    const parts = text.split(' ');
    
    if (parts.length < 6) {
        await ctx.reply('⚠️ **Usage:** `/add_page_button <page> <id> <text> <icon> <color> <action>`\n\n📝 Example: `/add_page_button transfer transfer_btn Transfer fa-paper-plane green sendTransfer()`');
        return;
    }
    
    const page = parts[0];
    const buttonId = parts[1];
    const buttonText = parts[2];
    const icon = parts[3];
    const color = parts[4];
    const action = parts.slice(5).join(' ');
    
    let pageHtml = await getFileFromGitHub(`public/${page}.html`);
    if (!pageHtml) {
        await ctx.reply(`❌ Page \`${page}\` not found`);
        return;
    }
    
    const newButton = `<button id="${buttonId}" class="bg-${color}-500 text-white py-2 rounded-xl w-full mt-2" onclick="${action}"><i class="fa-solid ${icon} ml-2"></i>${buttonText}</button>`;
    
    let newHtml;
    if (pageHtml.includes('<div id="pageContent">')) {
        newHtml = pageHtml.replace('<div id="pageContent">', `<div id="pageContent">\n${newButton}`);
    } else {
        newHtml = pageHtml.replace('<div class="space-y-4">', `<div class="space-y-4">\n${newButton}`);
    }
    
    if (await uploadToGitHub(`public/${page}.html`, newHtml, `Add button: ${buttonText} to ${page}`)) {
        await triggerRenderDeploy();
        await ctx.reply(`✅ **Button \`${buttonText}\` added to page \`${page}\`**`);
    } else {
        await ctx.reply('❌ Failed to add button');
    }
});

// Deploy command
bot.command('deploy', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    await ctx.reply('🚀 **Triggering deployment...**');
    
    if (await triggerRenderDeploy()) {
        await ctx.reply(`✅ **Deployment started!**\n\n🌐 ${RENDER_CONFIG.url}\n⏱️ Ready in 1-2 minutes`);
    } else {
        await ctx.reply('❌ Failed to trigger deployment');
    }
});

// Deploy to KataBump
bot.command('deploy_katabump', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    await ctx.reply('🚀 **Uploading to KataBump...**');
    
    try {
        const serverContent = await getFileFromGitHub('server.js');
        const packageContent = await getFileFromGitHub('package.json');
        const indexContent = await getFileFromGitHub('index.html');
        
        if (serverContent) await uploadToKataBump(serverContent, 'server.js');
        if (packageContent) await uploadToKataBump(packageContent, 'package.json');
        if (indexContent) await uploadToKataBump(indexContent, 'index.html');
        
        await ctx.reply(`✅ **Files uploaded to KataBump!**\n\n🌐 ${KATABUMP_CONFIG.web_url}\n🔄 Server will restart automatically`);
    } catch (error) {
        await ctx.reply(`❌ Failed: ${error.message}`);
    }
});

// Sync all platforms
bot.command('sync_all', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    await ctx.reply('🔄 **Syncing all platforms...**\n\n1️⃣ GitHub → Render\n2️⃣ GitHub → KataBump');
    
    const renderResult = await triggerRenderDeploy();
    
    try {
        const serverContent = await getFileFromGitHub('server.js');
        if (serverContent) await uploadToKataBump(serverContent, 'server.js');
    } catch (e) {}
    
    await ctx.reply(`
✅ **Sync completed!**

🌐 **Render:** ${RENDER_CONFIG.url}
🌐 **KataBump:** ${KATABUMP_CONFIG.web_url}
📁 **GitHub:** https://github.com/${GITHUB_CONFIG.owner}/${GITHUB_CONFIG.repo}

⏱️ Updates may take 1-2 minutes
    `);
});

// Add service interactive
bot.command('add_service', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    await ctx.reply(`
📝 **Add New Service**

Send service data in following format:

\`establishment: Business Name\`
\`productName: Product/Service Name\`
\`category: services\`
\`basePrice: 100\`
\`currency: YER\`
\`contact: 967700000000\`
\`description: Service description\`
\`discountPercent: 0\`

💡 You can also send an image with the message
    `);
    
    // Store in session
    ctx.session.waitingForService = true;
});

// List services
bot.command('list_services', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    await ctx.reply('📦 **Fetching services...**');
    
    try {
        const response = await fetch(`${RENDER_CONFIG.url}/api/services`);
        const data = await response.json();
        
        if (data.success && data.services.length > 0) {
            let text = `📦 **Services (${data.services.length})**\n\n`;
            for (const s of data.services.slice(0, 20)) {
                text += `🆔 \`${s.id.slice(0, 15)}...\` | 📌 ${s.productName?.slice(0, 20)} | 💰 ${s.price}\n`;
            }
            if (data.services.length > 20) {
                text += `\n... and ${data.services.length - 20} more`;
            }
            await ctx.reply(text);
        } else {
            await ctx.reply('📦 **No services found**');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Delete service
bot.command('delete_service', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const serviceId = ctx.message.text.replace('/delete_service', '').trim();
    if (!serviceId) {
        await ctx.reply('⚠️ **Usage:** `/delete_service <service_id>`');
        return;
    }
    
    await ctx.reply(`🗑️ **Deleting service...**`);
    
    try {
        const response = await fetch(`${RENDER_CONFIG.url}/api/services/${serviceId}`, {
            method: 'DELETE',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ uid: ADMIN_ID.toString() })
        });
        
        if (response.ok) {
            await ctx.reply(`✅ **Service \`${serviceId}\` deleted**`);
        } else {
            await ctx.reply('❌ Failed to delete service');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Approve service
bot.command('approve_service', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const serviceId = ctx.message.text.replace('/approve_service', '').trim();
    if (!serviceId) {
        await ctx.reply('⚠️ **Usage:** `/approve_service <service_id>`');
        return;
    }
    
    await ctx.reply(`✅ **Approving service...**`);
    
    try {
        const response = await fetch(`${RENDER_CONFIG.url}/api/admin/services/${serviceId}/approve`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ adminUid: ADMIN_ID.toString() })
        });
        
        if (response.ok) {
            await ctx.reply(`✅ **Service \`${serviceId}\` approved**`);
        } else {
            await ctx.reply('❌ Failed to approve service');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Reject service
bot.command('reject_service', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const text = ctx.message.text.replace('/reject_service', '').trim();
    const parts = text.split(' ');
    const serviceId = parts[0];
    const reason = parts.slice(1).join(' ') || 'Not specified';
    
    if (!serviceId) {
        await ctx.reply('⚠️ **Usage:** `/reject_service <service_id> [reason]`');
        return;
    }
    
    await ctx.reply(`❌ **Rejecting service...**`);
    
    try {
        const response = await fetch(`${RENDER_CONFIG.url}/api/admin/services/${serviceId}/reject`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ adminUid: ADMIN_ID.toString(), reason })
        });
        
        if (response.ok) {
            await ctx.reply(`✅ **Service \`${serviceId}\` rejected**\n📝 Reason: ${reason}`);
        } else {
            await ctx.reply('❌ Failed to reject service');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Add points
bot.command('add_points', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const parts = ctx.message.text.replace('/add_points', '').trim().split(' ');
    if (parts.length !== 2) {
        await ctx.reply('⚠️ **Usage:** `/add_points <user_id> <amount>`');
        return;
    }
    
    const userId = parts[0];
    const amount = parseInt(parts[1]);
    
    if (isNaN(amount)) {
        await ctx.reply('❌ Amount must be a number');
        return;
    }
    
    await ctx.reply(`💎 **Adding ${amount} points to user...**`);
    
    try {
        const response = await fetch(`${RENDER_CONFIG.url}/api/users/${userId}/points`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount, reason: 'admin_add', adminId: ADMIN_ID.toString() })
        });
        
        if (response.ok) {
            await ctx.reply(`✅ **${amount} points added to user \`${userId}\`**`);
        } else {
            await ctx.reply('❌ Failed to add points');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Remove points
bot.command('remove_points', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const parts = ctx.message.text.replace('/remove_points', '').trim().split(' ');
    if (parts.length !== 2) {
        await ctx.reply('⚠️ **Usage:** `/remove_points <user_id> <amount>`');
        return;
    }
    
    const userId = parts[0];
    const amount = parseInt(parts[1]);
    
    if (isNaN(amount)) {
        await ctx.reply('❌ Amount must be a number');
        return;
    }
    
    await ctx.reply(`💎 **Removing ${amount} points from user...**`);
    
    try {
        const response = await fetch(`${RENDER_CONFIG.url}/api/users/${userId}/points`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ amount: -amount, reason: 'admin_remove', adminId: ADMIN_ID.toString() })
        });
        
        if (response.ok) {
            await ctx.reply(`✅ **${amount} points removed from user \`${userId}\`**`);
        } else {
            await ctx.reply('❌ Failed to remove points');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// View users
bot.command('view_users', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    await ctx.reply('👥 **Fetching users...**');
    
    try {
        const response = await fetch(`${RENDER_CONFIG.url}/api/users`);
        const data = await response.json();
        
        if (data.success && data.users && data.users.length > 0) {
            let text = `👥 **Users (${data.users.length})**\n\n`;
            for (const u of data.users.slice(0, 20)) {
                text += `🆔 \`${u.id.slice(0, 15)}...\` | ⭐ ${u.points || 0} | 👤 ${u.name || 'No name'}\n`;
            }
            if (data.users.length > 20) {
                text += `\n... and ${data.users.length - 20} more`;
            }
            await ctx.reply(text);
        } else {
            await ctx.reply('👥 **No users found**');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Find user
bot.command('find_user', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const userId = ctx.message.text.replace('/find_user', '').trim();
    if (!userId) {
        await ctx.reply('⚠️ **Usage:** `/find_user <user_id>`');
        return;
    }
    
    await ctx.reply(`🔍 **Searching for user...**`);
    
    try {
        const response = await fetch(`${RENDER_CONFIG.url}/api/users/${userId}`);
        const data = await response.json();
        
        if (data.success && data.user) {
            const u = data.user;
            await ctx.reply(`
✅ **User Found**

🆔 ID: \`${u.id}\`
👤 Name: ${u.name || 'Not set'}
📞 Phone: ${u.phone || 'Not set'}
⭐ Points: ${u.points || 0}
🎭 Role: ${u.role || 'user'}
📅 Joined: ${u.createdAt ? new Date(u.createdAt).toLocaleDateString() : 'Unknown'}
            `);
        } else {
            await ctx.reply(`❌ User not found: \`${userId}\``);
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Give admin
bot.command('give_admin', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const userId = ctx.message.text.replace('/give_admin', '').trim();
    if (!userId) {
        await ctx.reply('⚠️ **Usage:** `/give_admin <user_id>`');
        return;
    }
    
    await ctx.reply(`👑 **Making user admin...**`);
    
    try {
        const response = await fetch(`${RENDER_CONFIG.url}/api/users/${userId}/role`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role: 'admin', adminId: ADMIN_ID.toString() })
        });
        
        if (response.ok) {
            await ctx.reply(`✅ **User \`${userId}\` is now an admin**`);
        } else {
            await ctx.reply('❌ Failed to update role');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Stats
bot.command('stats', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    await ctx.reply('📊 **Fetching statistics...**');
    
    try {
        const statsResponse = await fetch(`${RENDER_CONFIG.url}/api/admin/dashboard/stats?adminUid=${ADMIN_ID}`);
        const stats = await statsResponse.json();
        
        await ctx.reply(`
📊 **System Statistics**

👥 **Users:** ${stats.total?.users || 0}
📦 **Services:** ${stats.total?.services || 0}
🛒 **Orders:** ${stats.total?.orders || 0}
⏳ **Pending Services:** ${stats.total?.pendingServices || 0}
🚨 **Pending Reports:** ${stats.total?.pendingReports || 0}
⭐ **Total Points:** ${stats.total?.totalPoints?.toLocaleString() || 0}

📈 **Today:**
- New Orders: ${stats.today?.orders || 0}
- New Users: ${stats.today?.users || 0}

🕐 **Last Updated:** ${new Date().toLocaleString()}
        `);
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Backup
bot.command('backup', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    await ctx.reply('💾 **Creating backup...**');
    
    try {
        const response = await fetch(`${RENDER_CONFIG.url}/api/admin/backup?adminUid=${ADMIN_ID}`);
        const backup = await response.json();
        
        if (backup.success) {
            await ctx.reply(`
✅ **Backup created successfully!**

🆔 ID: \`${backup.backupId}\`
📦 Services: ${backup.stats?.services || 0}
👥 Users: ${backup.stats?.users || 0}
🛒 Orders: ${backup.stats?.orders || 0}
📅 Date: ${new Date().toLocaleString()}

💾 Backup stored in Firebase
            `);
        } else {
            await ctx.reply('❌ Failed to create backup');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Status
bot.command('status', async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const statuses = [];
    
    // Check Render
    try {
        const renderHealth = await fetch(`${RENDER_CONFIG.url}/health`);
        statuses.push(renderHealth.ok ? '✅ Render: Online' : '❌ Render: Offline');
    } catch {
        statuses.push('❌ Render: Offline');
    }
    
    // Check KataBump
    try {
        const kataBumpHealth = await fetch(`${KATABUMP_CONFIG.web_url}/health`);
        statuses.push(kataBumpHealth.ok ? '✅ KataBump: Online' : '❌ KataBump: Offline');
    } catch {
        statuses.push('❌ KataBump: Offline');
    }
    
    // Check GitHub
    try {
        const githubCheck = await fetch(`https://api.github.com/repos/${GITHUB_CONFIG.owner}/${GITHUB_CONFIG.repo}`, {
            headers: { 'Authorization': `token ${GITHUB_CONFIG.token}` }
        });
        statuses.push(githubCheck.ok ? '✅ GitHub: Online' : '❌ GitHub: Offline');
    } catch {
        statuses.push('❌ GitHub: Offline');
    }
    
    await ctx.reply(`
📊 **System Status**

${statuses.join('\n')}

🌐 **URLs:**
- Render: ${RENDER_CONFIG.url}
- KataBump: ${KATABUMP_CONFIG.web_url}
- GitHub: https://github.com/${GITHUB_CONFIG.owner}/${GITHUB_CONFIG.repo}

🕐 **Last Check:** ${new Date().toLocaleString()}
    `);
});

// Message handler for file uploads
bot.on(message('document'), async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const file = ctx.message.document;
    const fileId = file.file_id;
    const fileName = file.file_name;
    
    await ctx.reply(`📁 **Received file: \`${fileName}\`**\n⏳ Uploading to GitHub...`);
    
    try {
        const fileLink = await ctx.telegram.getFileLink(fileId);
        const response = await fetch(fileLink.href);
        const content = await response.text();
        
        let uploadPath = '';
        if (fileName.endsWith('.html')) uploadPath = `public/${fileName}`;
        else if (fileName.endsWith('.js')) uploadPath = `public/${fileName}`;
        else uploadPath = fileName;
        
        if (await uploadToGitHub(uploadPath, content, `Upload via bot: ${fileName}`)) {
            await triggerRenderDeploy();
            await ctx.reply(`✅ **File \`${fileName}\` uploaded to GitHub**\n🚀 Deployment triggered`);
        } else {
            await ctx.reply('❌ Failed to upload file');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

bot.on(message('photo'), async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    
    const photo = ctx.message.photo[ctx.message.photo.length - 1];
    const fileId = photo.file_id;
    
    await ctx.reply('🖼️ **Received image**\n⏳ Uploading to GitHub...');
    
    try {
        const fileLink = await ctx.telegram.getFileLink(fileId);
        const response = await fetch(fileLink.href);
        const buffer = await response.arrayBuffer();
        const base64 = Buffer.from(buffer).toString('base64');
        
        const fileName = `image_${Date.now()}.jpg`;
        
        if (await uploadToGitHub(`images/${fileName}`, base64, `Upload image: ${fileName}`)) {
            await ctx.reply(`✅ **Image uploaded**\n🔗 ${RENDER_CONFIG.url}/images/${fileName}`);
        } else {
            await ctx.reply('❌ Failed to upload image');
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
});

// Handle service creation input
bot.on(message('text'), async (ctx) => {
    if (ctx.from.id !== ADMIN_ID) return;
    if (!ctx.session.waitingForService) return;
    
    const text = ctx.message.text;
    const lines = text.split('\n');
    const serviceData = {};
    
    for (const line of lines) {
        const colonIndex = line.indexOf(':');
        if (colonIndex > 0) {
            const key = line.substring(0, colonIndex).trim();
            const value = line.substring(colonIndex + 1).trim();
            if (key && value) {
                serviceData[key] = value;
            }
        }
    }
    
    if (!serviceData.establishment || !serviceData.productName || !serviceData.basePrice || !serviceData.contact) {
        await ctx.reply('❌ Missing required fields: establishment, productName, basePrice, contact');
        ctx.session.waitingForService = false;
        return;
    }
    
    await ctx.reply('📝 **Creating service...**');
    
    try {
        const response = await fetch(`${RENDER_CONFIG.url}/api/services/create`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                uid: ADMIN_ID.toString(),
                serviceData: {
                    establishment: serviceData.establishment,
                    productName: serviceData.productName,
                    description: serviceData.description || '',
                    category_id: serviceData.category || 'services',
                    category_name: getCategoryName(serviceData.category || 'services'),
                    basePrice: parseFloat(serviceData.basePrice),
                    discountPercent: parseFloat(serviceData.discountPercent) || 0,
                    currency: serviceData.currency || 'YER',
                    contact: serviceData.contact,
                    status: 'approved' // Auto-approve for admin
                }
            })
        });
        
        const result = await response.json();
        
        if (result.success) {
            await ctx.reply(`✅ **Service created successfully!**\n🆔 ID: \`${result.serviceId}\``);
        } else {
            await ctx.reply(`❌ Failed: ${result.error}`);
        }
    } catch (error) {
        await ctx.reply(`❌ Error: ${error.message}`);
    }
    
    ctx.session.waitingForService = false;
});

function getCategoryName(catId) {
    const categories = {
        health: '🏥 Health & Hospitals',
        finance: '💰 Financial Services',
        hotels: '🏨 Hotels & Tourism',
        restaurants: '🍽️ Restaurants',
        fashion: '👗 Fashion',
        realestate: '🏠 Real Estate',
        education: '📚 Education',
        services: '🛠️ General Services'
    };
    return categories[catId] || '🛠️ General Services';
}

// Launch bot
bot.launch().then(() => {
    console.log('='.repeat(60));
    console.log('🤖 Telegram Bot Started');
    console.log(`👑 Admin ID: ${ADMIN_ID}`);
    console.log('='.repeat(60));
}).catch(console.error);

// Enable graceful stop
process.once('SIGINT', () => bot.stop('SIGINT'));
process.once('SIGTERM', () => bot.stop('SIGTERM'));