const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const compression = require('compression');
const rateLimit = require('express-rate-limit');
const path = require('path');
const admin = require('firebase-admin');
const { v4: uuidv4 } = require('uuid');
require('dotenv').config();

// ========== إعدادات Express ==========
const app = express();

// Security middleware
app.use(helmet({
    contentSecurityPolicy: false,
    crossOriginEmbedderPolicy: false
}));
app.use(compression());
app.use(cors({
    origin: '*',
    methods: ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization']
}));
app.use(express.json({ limit: '50mb' }));
app.use(express.urlencoded({ extended: true, limit: '50mb' }));

// Rate limiting
const limiter = rateLimit({
    windowMs: 15 * 60 * 1000, // 15 minutes
    max: 100, // Limit each IP to 100 requests per windowMs
    message: { error: 'Too many requests, please try again later.' }
});
app.use('/api/', limiter);

// ========== Firebase Admin Initialization ==========
const serviceAccount = require('./firebase-service-account.json');

admin.initializeApp({
    credential: admin.credential.cert(serviceAccount),
    storageBucket: process.env.FIREBASE_STORAGE_BUCKET,
    databaseURL: process.env.FIREBASE_DATABASE_URL
});

const db = admin.firestore();
const storage = admin.storage().bucket();
const messaging = admin.messaging();
const FieldValue = admin.firestore.FieldValue;
const auth = admin.auth();

// ========== Helper Functions ==========
function generateId(prefix = '') {
    return `${prefix}${Date.now()}_${uuidv4().slice(0, 8)}`;
}

function formatDate(timestamp) {
    if (!timestamp) return null;
    if (timestamp.toDate) return timestamp.toDate().toISOString();
    return new Date(timestamp).toISOString();
}

async function sendNotification({ userId, type, title, body, data = {} }) {
    try {
        const notifRef = db.collection('notifications').doc();
        await notifRef.set({
            id: notifRef.id,
            userId,
            type,
            title,
            body,
            data,
            read: false,
            createdAt: FieldValue.serverTimestamp()
        });

        const userDoc = await db.collection('users').doc(userId).get();
        const fcmToken = userDoc.data()?.fcmToken;
        
        if (fcmToken) {
            await messaging.send({
                token: fcmToken,
                notification: { title, body },
                data: { ...data, type, notifId: notifRef.id },
                android: { priority: 'high' }
            });
        }
        
        return { success: true, notifId: notifRef.id };
    } catch (error) {
        console.error('Notification Error:', error);
        return { success: false, error: error.message };
    }
}

async function updateWallet(uid, amount, type, refType, refId, description) {
    const userRef = db.collection('users').doc(uid);
    
    return await db.runTransaction(async (t) => {
        const userDoc = await t.get(userRef);
        if (!userDoc.exists) throw new Error('User not found');
        
        const currentPoints = userDoc.data().points || 0;
        const newBalance = currentPoints + amount;
        
        if (newBalance < 0) throw new Error('Insufficient points');
        if (userDoc.data().walletFrozen) throw new Error('Wallet is frozen');
        
        t.update(userRef, {
            points: newBalance,
            totalEarned: FieldValue.increment(amount > 0 ? amount : 0),
            totalSpent: FieldValue.increment(amount < 0 ? Math.abs(amount) : 0),
            lastTransactionAt: FieldValue.serverTimestamp()
        });
        
        const txnRef = db.collection('wallet_transactions').doc();
        t.set(txnRef, {
            id: txnRef.id,
            userId: uid,
            type,
            amount,
            balanceBefore: currentPoints,
            balanceAfter: newBalance,
            refType,
            refId,
            description,
            createdAt: FieldValue.serverTimestamp(),
            status: 'completed'
        });
        
        return { newBalance, txnId: txnRef.id };
    });
}

async function isAdmin(uid) {
    try {
        const userDoc = await db.collection('users').doc(uid).get();
        return userDoc.exists && userDoc.data().role === 'admin';
    } catch {
        return false;
    }
}

// ========== API: Create Service ==========
app.post('/api/services/create', async (req, res) => {
    try {
        const { uid, serviceData, imageBase64 } = req.body;
        
        if (!uid) return res.status(401).json({ error: 'Unauthorized' });
        
        const userDoc = await db.collection('users').doc(uid).get();
        if (!userDoc.exists) return res.status(401).json({ error: 'User not found' });
        
        const user = userDoc.data();
        
        // Check daily limit
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const todayServices = await db.collection('services')
            .where('userId', '==', uid)
            .where('createdAt', '>=', today)
            .get();
        
        if (todayServices.size >= 3) {
            return res.status(429).json({ error: 'Daily limit of 3 services reached' });
        }
        
        // Upload image
        let imageUrl = '';
        if (imageBase64) {
            const matches = imageBase64.match(/^data:([A-Za-z-+\/]+);base64,(.+)$/);
            if (matches && matches.length === 3) {
                const buffer = Buffer.from(matches[2], 'base64');
                const fileName = `services/${uid}/${Date.now()}.jpg`;
                const file = storage.file(fileName);
                await file.save(buffer, { contentType: 'image/jpeg' });
                await file.makePublic();
                imageUrl = `https://storage.googleapis.com/${storage.name}/${fileName}`;
            }
        }
        
        // Calculate final price
        const basePrice = parseFloat(serviceData.basePrice);
        const discountPercent = parseFloat(serviceData.discountPercent) || 0;
        const finalPrice = discountPercent > 0 ? basePrice * (1 - discountPercent / 100) : basePrice;
        
        const serviceId = generateId('srv_');
        const newService = {
            id: serviceId,
            ...serviceData,
            basePrice,
            discountPercent,
            price: parseFloat(finalPrice.toFixed(2)),
            image: imageUrl,
            userId: uid,
            deviceId: user.deviceId,
            status: serviceData.status || 'pending',
            views: 0,
            avgRating: 0,
            reviewCount: 0,
            createdAt: FieldValue.serverTimestamp(),
            updatedAt: FieldValue.serverTimestamp()
        };
        
        await db.collection('services').doc(serviceId).set(newService);
        
        // Add points reward
        if (serviceData.status !== 'draft') {
            await updateWallet(uid, 10, 'earn', 'service', serviceId, 'Added new service +10 points');
        }
        
        // Notify admins
        const admins = await db.collection('users').where('role', '==', 'admin').get();
        admins.forEach(async (adminDoc) => {
            await sendNotification({
                userId: adminDoc.id,
                type: 'admin',
                title: '🆕 New Service Pending',
                body: `${serviceData.establishment} - ${serviceData.productName}`,
                data: { serviceId, action: 'review' }
            });
        });
        
        res.json({ success: true, serviceId, service: newService });
        
    } catch (error) {
        console.error('Create Service Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Get Services ==========
app.get('/api/services', async (req, res) => {
    try {
        const { category, status, userId, limit = 50, lastDocId } = req.query;
        
        let query = db.collection('services');
        
        if (category) query = query.where('category_id', '==', category);
        if (status) query = query.where('status', '==', status);
        if (userId) query = query.where('userId', '==', userId);
        
        query = query.orderBy('createdAt', 'desc').limit(parseInt(limit));
        
        const snapshot = await query.get();
        const services = snapshot.docs.map(doc => ({
            id: doc.id,
            ...doc.data(),
            createdAt: formatDate(doc.data().createdAt)
        }));
        
        res.json({ success: true, services, count: services.length });
    } catch (error) {
        console.error('Get Services Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Get Single Service ==========
app.get('/api/services/:serviceId', async (req, res) => {
    try {
        const { serviceId } = req.params;
        
        const serviceDoc = await db.collection('services').doc(serviceId).get();
        if (!serviceDoc.exists) {
            return res.status(404).json({ error: 'Service not found' });
        }
        
        // Increment views
        await serviceDoc.ref.update({ views: FieldValue.increment(1) });
        
        const service = { id: serviceDoc.id, ...serviceDoc.data() };
        service.createdAt = formatDate(service.createdAt);
        
        res.json({ success: true, service });
    } catch (error) {
        console.error('Get Service Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Update Service ==========
app.put('/api/services/:serviceId', async (req, res) => {
    try {
        const { serviceId } = req.params;
        const { uid, updates } = req.body;
        
        const serviceDoc = await db.collection('services').doc(serviceId).get();
        if (!serviceDoc.exists) return res.status(404).json({ error: 'Service not found' });
        
        const service = serviceDoc.data();
        if (service.userId !== uid && !(await isAdmin(uid))) {
            return res.status(403).json({ error: 'Unauthorized' });
        }
        
        await serviceDoc.ref.update({
            ...updates,
            updatedAt: FieldValue.serverTimestamp()
        });
        
        res.json({ success: true });
    } catch (error) {
        console.error('Update Service Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Delete Service ==========
app.delete('/api/services/:serviceId', async (req, res) => {
    try {
        const { serviceId } = req.params;
        const { uid } = req.body;
        
        const serviceDoc = await db.collection('services').doc(serviceId).get();
        if (!serviceDoc.exists) return res.status(404).json({ error: 'Service not found' });
        
        const service = serviceDoc.data();
        if (service.userId !== uid && !(await isAdmin(uid))) {
            return res.status(403).json({ error: 'Unauthorized' });
        }
        
        // Delete image from storage if exists
        if (service.image && service.image.includes('storage.googleapis.com')) {
            const fileName = service.image.split(`${storage.name}/`)[1];
            if (fileName) {
                await storage.file(fileName).delete().catch(console.error);
            }
        }
        
        await serviceDoc.ref.delete();
        
        res.json({ success: true });
    } catch (error) {
        console.error('Delete Service Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Reserve Service ==========
app.post('/api/orders/reserve', async (req, res) => {
    try {
        const { uid, serviceId, couponCode } = req.body;
        
        const [userDoc, serviceDoc] = await Promise.all([
            db.collection('users').doc(uid).get(),
            db.collection('services').doc(serviceId).get()
        ]);
        
        if (!serviceDoc.exists) return res.status(404).json({ error: 'Service not found' });
        
        const service = serviceDoc.data();
        const user = userDoc.data();
        
        if (service.userId === uid) {
            return res.status(400).json({ error: 'Cannot reserve your own service' });
        }
        
        const basePrice = parseFloat(service.price);
        let depositPoints = Math.ceil(basePrice * 0.15 * 10);
        let discountApplied = 0;
        
        // Apply coupon
        if (couponCode) {
            const couponSnap = await db.collection('coupons')
                .where('code', '==', couponCode.toUpperCase())
                .where('isActive', '==', true)
                .limit(1)
                .get();
            
            if (!couponSnap.empty) {
                const coupon = couponSnap.docs[0].data();
                if (coupon.expiresAt?.toDate() > new Date()) {
                    discountApplied = basePrice * (coupon.value / 100);
                    depositPoints = Math.ceil((basePrice - discountApplied) * 0.15 * 10);
                }
            }
        }
        
        if ((user.points || 0) < depositPoints) {
            return res.status(400).json({ error: 'Insufficient points' });
        }
        
        // Deduct points
        await updateWallet(uid, -depositPoints, 'spend', 'order', serviceId,
            `Deposit for ${service.productName} - Discount: ${discountApplied.toFixed(2)}`);
        
        // Create order
        const orderId = generateId('ord_');
        const order = {
            id: orderId,
            buyerId: uid,
            buyerName: user.name,
            buyerPhone: user.phone,
            sellerId: service.userId,
            sellerName: service.establishment,
            serviceId,
            serviceName: service.productName,
            servicePrice: basePrice,
            currency: service.currency,
            depositPoints,
            discountApplied,
            couponUsed: couponCode || null,
            status: 'reserved',
            expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000),
            createdAt: FieldValue.serverTimestamp(),
            updatedAt: FieldValue.serverTimestamp()
        };
        
        await db.collection('orders').doc(orderId).set(order);
        
        // Notifications
        await sendNotification({
            userId: service.userId,
            type: 'order',
            title: '🔔 New Reservation!',
            body: `${user.name} reserved ${service.productName}. Deposit: ${depositPoints} points`,
            data: { orderId, action: 'view_order' }
        });
        
        await sendNotification({
            userId: uid,
            type: 'order',
            title: '✅ Reservation Successful',
            body: `${depositPoints} points deducted. Contact seller to complete purchase`,
            data: { orderId, sellerPhone: service.contact }
        });
        
        const whatsappMsg = `🏢 *New Order Reservation*\n📦 Product: ${service.productName}\n🆔 Order ID: ${orderId}\n💰 Price: ${basePrice} ${service.currency}\n💎 Deposit Paid: ${depositPoints} points\n\n👤 *Buyer Info*\nName: ${user.name}\nPhone: ${user.phone}\n\nPlease contact to complete the purchase.`;
        
        res.json({
            success: true,
            orderId,
            depositPoints,
            sellerContact: service.contact,
            whatsappMsg
        });
        
    } catch (error) {
        console.error('Reserve Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Update Order Status ==========
app.put('/api/orders/:orderId/status', async (req, res) => {
    try {
        const { orderId } = req.params;
        const { uid, status } = req.body;
        
        const orderDoc = await db.collection('orders').doc(orderId).get();
        if (!orderDoc.exists) return res.status(404).json({ error: 'Order not found' });
        
        const order = orderDoc.data();
        const isAdminUser = await isAdmin(uid);
        
        if (order.buyerId !== uid && order.sellerId !== uid && !isAdminUser) {
            return res.status(403).json({ error: 'Unauthorized' });
        }
        
        const allowedStatuses = ['confirmed', 'completed', 'cancelled'];
        if (!allowedStatuses.includes(status)) {
            return res.status(400).json({ error: 'Invalid status' });
        }
        
        await orderDoc.ref.update({
            status,
            updatedAt: FieldValue.serverTimestamp(),
            ...(status === 'completed' ? { completedAt: FieldValue.serverTimestamp() } : {})
        });
        
        // Handle completed order - release deposit to seller
        if (status === 'completed') {
            // 50% of deposit goes to seller
            const sellerBonus = Math.floor(order.depositPoints * 0.5);
            if (sellerBonus > 0) {
                await updateWallet(order.sellerId, sellerBonus, 'earn', 'order_complete', orderId,
                    `Order completion bonus: ${sellerBonus} points`);
            }
        }
        
        // Notify other party
        const notifyUserId = status === 'confirmed' ? order.buyerId : 
                            (status === 'completed' ? order.sellerId : 
                            (status === 'cancelled' ? (uid === order.buyerId ? order.sellerId : order.buyerId) : null));
        
        if (notifyUserId) {
            await sendNotification({
                userId: notifyUserId,
                type: 'order',
                title: `📦 Order ${status === 'confirmed' ? 'Confirmed' : status === 'completed' ? 'Completed' : 'Cancelled'}`,
                body: `Order #${orderId.slice(-8)} has been ${status}`,
                data: { orderId, status }
            });
        }
        
        res.json({ success: true });
    } catch (error) {
        console.error('Update Order Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Get User Orders ==========
app.get('/api/orders/:uid', async (req, res) => {
    try {
        const { uid } = req.params;
        const { role = 'buyer', limit = 50 } = req.query;
        
        const field = role === 'buyer' ? 'buyerId' : 'sellerId';
        const snapshot = await db.collection('orders')
            .where(field, '==', uid)
            .orderBy('createdAt', 'desc')
            .limit(parseInt(limit))
            .get();
        
        const orders = snapshot.docs.map(doc => ({
            id: doc.id,
            ...doc.data(),
            createdAt: formatDate(doc.data().createdAt),
            updatedAt: formatDate(doc.data().updatedAt)
        }));
        
        res.json({ success: true, orders });
    } catch (error) {
        console.error('Get Orders Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Create Review ==========
app.post('/api/reviews/create', async (req, res) => {
    try {
        const { uid, serviceId, orderId, rating, comment } = req.body;
        
        // Verify order completion
        const orderDoc = await db.collection('orders').doc(orderId).get();
        if (!orderDoc.exists) return res.status(404).json({ error: 'Order not found' });
        if (orderDoc.data().buyerId !== uid) return res.status(403).json({ error: 'Unauthorized' });
        if (orderDoc.data().status !== 'completed') return res.status(400).json({ error: 'Order must be completed first' });
        
        // Check for existing review
        const existingReview = await db.collection('reviews')
            .where('orderId', '==', orderId)
            .limit(1)
            .get();
        
        if (!existingReview.empty) {
            return res.status(400).json({ error: 'Already reviewed this order' });
        }
        
        const reviewId = generateId('rev_');
        const review = {
            id: reviewId,
            userId: uid,
            serviceId,
            orderId,
            rating: Math.min(5, Math.max(1, parseInt(rating))),
            comment: comment || '',
            helpful: 0,
            reported: false,
            createdAt: FieldValue.serverTimestamp()
        };
        
        await db.collection('reviews').doc(reviewId).set(review);
        
        // Update service average rating
        const reviewsSnap = await db.collection('reviews')
            .where('serviceId', '==', serviceId)
            .get();
        
        const avgRating = reviewsSnap.docs.reduce((sum, d) => sum + d.data().rating, 0) / reviewsSnap.size;
        
        await db.collection('services').doc(serviceId).update({
            avgRating: parseFloat(avgRating.toFixed(1)),
            reviewCount: reviewsSnap.size,
            lastReviewAt: FieldValue.serverTimestamp()
        });
        
        // Reward points
        await updateWallet(uid, 5, 'earn', 'review', reviewId, 'Product review reward +5 points');
        
        // Notify seller
        const serviceDoc = await db.collection('services').doc(serviceId).get();
        await sendNotification({
            userId: serviceDoc.data().userId,
            type: 'review',
            title: '⭐ New Review',
            body: `Your product "${serviceDoc.data().productName}" received ${rating} stars`,
            data: { reviewId, serviceId, rating }
        });
        
        res.json({ success: true, reviewId });
    } catch (error) {
        console.error('Create Review Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Get Service Reviews ==========
app.get('/api/reviews/:serviceId', async (req, res) => {
    try {
        const { serviceId } = req.params;
        const { limit = 20 } = req.query;
        
        const snapshot = await db.collection('reviews')
            .where('serviceId', '==', serviceId)
            .orderBy('createdAt', 'desc')
            .limit(parseInt(limit))
            .get();
        
        const reviews = await Promise.all(snapshot.docs.map(async (doc) => {
            const review = doc.data();
            const userDoc = await db.collection('users').doc(review.userId).get();
            return {
                id: doc.id,
                ...review,
                userName: userDoc.data()?.name || 'User',
                userAvatar: userDoc.data()?.avatar || null,
                createdAt: formatDate(review.createdAt)
            };
        }));
        
        res.json({ success: true, reviews });
    } catch (error) {
        console.error('Get Reviews Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Create Report ==========
app.post('/api/reports/create', async (req, res) => {
    try {
        const { uid, targetType, targetId, reason, description } = req.body;
        
        // Check for duplicate report within 24 hours
        const recentReport = await db.collection('reports')
            .where('reporterId', '==', uid)
            .where('targetId', '==', targetId)
            .where('createdAt', '>', new Date(Date.now() - 24 * 60 * 60 * 1000))
            .limit(1)
            .get();
        
        if (!recentReport.empty) {
            return res.status(429).json({ error: 'Already reported this item within 24 hours' });
        }
        
        const reportId = generateId('rpt_');
        const report = {
            id: reportId,
            reporterId: uid,
            targetType,
            targetId,
            reason,
            description: description || '',
            status: 'pending',
            createdAt: FieldValue.serverTimestamp(),
            updatedAt: FieldValue.serverTimestamp()
        };
        
        await db.collection('reports').doc(reportId).set(report);
        
        // Auto-moderation: Hide service if 3+ reports in 1 hour
        let autoResolved = false;
        if (targetType === 'service') {
            const recentReports = await db.collection('reports')
                .where('targetId', '==', targetId)
                .where('createdAt', '>', new Date(Date.now() - 60 * 60 * 1000))
                .get();
            
            if (recentReports.size >= 3) {
                await db.collection('services').doc(targetId).update({ 
                    status: 'hidden',
                    hiddenAt: FieldValue.serverTimestamp(),
                    hiddenReason: 'auto_moderation'
                });
                autoResolved = true;
            }
        }
        
        // Notify admins
        const admins = await db.collection('users').where('role', '==', 'admin').get();
        admins.forEach(async (adminDoc) => {
            await sendNotification({
                userId: adminDoc.id,
                type: 'admin',
                title: '🚨 New Report',
                body: `Report on ${targetType}: ${reason}`,
                data: { reportId, targetType, targetId }
            });
        });
        
        res.json({ success: true, reportId, autoResolved });
    } catch (error) {
        console.error('Create Report Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Admin Dashboard Stats ==========
app.get('/api/admin/dashboard/stats', async (req, res) => {
    try {
        const { adminUid } = req.query;
        
        if (!(await isAdmin(adminUid))) {
            return res.status(403).json({ error: 'Unauthorized' });
        }
        
        const [
            servicesCount,
            usersCount,
            ordersCount,
            pendingServicesCount,
            pendingReportsCount,
            totalPoints
        ] = await Promise.all([
            db.collection('services').count().get(),
            db.collection('users').count().get(),
            db.collection('orders').count().get(),
            db.collection('services').where('status', '==', 'pending').count().get(),
            db.collection('reports').where('status', '==', 'pending').count().get(),
            db.collection('users').get().then(snap => 
                snap.docs.reduce((sum, doc) => sum + (doc.data().points || 0), 0)
            )
        ]);
        
        // Today's stats
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const todayOrders = await db.collection('orders')
            .where('createdAt', '>=', today)
            .count()
            .get();
        
        const todayUsers = await db.collection('users')
            .where('createdAt', '>=', today)
            .count()
            .get();
        
        res.json({
            success: true,
            total: {
                services: servicesCount.data().count,
                users: usersCount.data().count,
                orders: ordersCount.data().count,
                pendingServices: pendingServicesCount.data().count,
                pendingReports: pendingReportsCount.data().count,
                totalPoints
            },
            today: {
                orders: todayOrders.data().count,
                users: todayUsers.data().count
            }
        });
    } catch (error) {
        console.error('Admin Stats Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Admin Approve Service ==========
app.put('/api/admin/services/:serviceId/approve', async (req, res) => {
    try {
        const { serviceId } = req.params;
        const { adminUid } = req.body;
        
        if (!(await isAdmin(adminUid))) {
            return res.status(403).json({ error: 'Unauthorized' });
        }
        
        const serviceDoc = await db.collection('services').doc(serviceId).get();
        if (!serviceDoc.exists) return res.status(404).json({ error: 'Service not found' });
        
        await serviceDoc.ref.update({
            status: 'approved',
            approvedAt: FieldValue.serverTimestamp(),
            approvedBy: adminUid
        });
        
        await sendNotification({
            userId: serviceDoc.data().userId,
            type: 'service',
            title: '✅ Service Approved',
            body: `Your service "${serviceDoc.data().productName}" is now live`,
            data: { serviceId }
        });
        
        res.json({ success: true });
    } catch (error) {
        console.error('Approve Service Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Admin Reject Service ==========
app.put('/api/admin/services/:serviceId/reject', async (req, res) => {
    try {
        const { serviceId } = req.params;
        const { adminUid, reason } = req.body;
        
        if (!(await isAdmin(adminUid))) {
            return res.status(403).json({ error: 'Unauthorized' });
        }
        
        const serviceDoc = await db.collection('services').doc(serviceId).get();
        if (!serviceDoc.exists) return res.status(404).json({ error: 'Service not found' });
        
        await serviceDoc.ref.update({
            status: 'rejected',
            rejectedAt: FieldValue.serverTimestamp(),
            rejectedBy: adminUid,
            rejectionReason: reason || 'Not specified'
        });
        
        await sendNotification({
            userId: serviceDoc.data().userId,
            type: 'service',
            title: '❌ Service Rejected',
            body: `Your service "${serviceDoc.data().productName}" was rejected. Reason: ${reason || 'Not specified'}`,
            data: { serviceId }
        });
        
        res.json({ success: true });
    } catch (error) {
        console.error('Reject Service Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Get Notifications ==========
app.get('/api/notifications/:uid', async (req, res) => {
    try {
        const { uid } = req.params;
        const { limit = 50 } = req.query;
        
        const snapshot = await db.collection('notifications')
            .where('userId', '==', uid)
            .orderBy('createdAt', 'desc')
            .limit(parseInt(limit))
            .get();
        
        const notifications = snapshot.docs.map(doc => ({
            id: doc.id,
            ...doc.data(),
            createdAt: formatDate(doc.data().createdAt)
        }));
        
        res.json({ success: true, notifications });
    } catch (error) {
        console.error('Get Notifications Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Mark Notification Read ==========
app.put('/api/notifications/:notifId/read', async (req, res) => {
    try {
        await db.collection('notifications').doc(req.params.notifId).update({ read: true });
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Get User Profile ==========
app.get('/api/users/:uid', async (req, res) => {
    try {
        const { uid } = req.params;
        const userDoc = await db.collection('users').doc(uid).get();
        
        if (!userDoc.exists) return res.status(404).json({ error: 'User not found' });
        
        const user = userDoc.data();
        delete user.fcmToken; // Remove sensitive data
        
        res.json({ success: true, user: { id: uid, ...user } });
    } catch (error) {
        console.error('Get User Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Update User Profile ==========
app.put('/api/users/:uid', async (req, res) => {
    try {
        const { uid } = req.params;
        const { name, phone, avatar } = req.body;
        
        const updates = {};
        if (name) updates.name = name;
        if (phone) updates.phone = phone;
        if (avatar) updates.avatar = avatar;
        updates.updatedAt = FieldValue.serverTimestamp();
        
        await db.collection('users').doc(uid).update(updates);
        
        res.json({ success: true });
    } catch (error) {
        console.error('Update User Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Track Referral ==========
app.post('/api/referral/track', async (req, res) => {
    try {
        const { newUserId, referralCode } = req.body;
        
        if (!referralCode) return res.json({ success: false, reason: 'no_code' });
        
        const referrerSnap = await db.collection('users')
            .where('referralCode', '==', referralCode.toUpperCase())
            .limit(1)
            .get();
        
        if (referrerSnap.empty) return res.json({ success: false, reason: 'invalid_code' });
        
        const referrer = referrerSnap.docs[0];
        const referrerId = referrer.id;
        
        if (referrerId === newUserId) return res.json({ success: false, reason: 'self_referral' });
        
        const existingRef = await db.collection('referrals')
            .where('referredId', '==', newUserId)
            .limit(1)
            .get();
        
        if (!existingRef.empty) return res.json({ success: false, reason: 'already_referred' });
        
        const bonusPoints = 50;
        
        await db.collection('referrals').add({
            referrerId,
            referredId: newUserId,
            referralCode,
            bonusGiven: bonusPoints,
            status: 'active',
            createdAt: FieldValue.serverTimestamp()
        });
        
        await updateWallet(referrerId, bonusPoints, 'earn', 'referral', newUserId, 
            `Referral bonus: ${bonusPoints} points`);
        
        await db.collection('users').doc(newUserId).update({ referredBy: referrerId });
        await db.collection('users').doc(referrerId).update({
            totalReferrals: FieldValue.increment(1),
            totalReferralEarnings: FieldValue.increment(bonusPoints)
        });
        
        await sendNotification({
            userId: referrerId,
            type: 'referral',
            title: '🎉 New Referral Bonus!',
            body: `Someone signed up with your code! +${bonusPoints} points`,
            data: { newUserId, bonus: bonusPoints }
        });
        
        res.json({ success: true, bonus: bonusPoints, referrerName: referrer.data().name });
    } catch (error) {
        console.error('Referral Track Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Get Referral Stats ==========
app.get('/api/referral/stats/:uid', async (req, res) => {
    try {
        const { uid } = req.params;
        
        const userDoc = await db.collection('users').doc(uid).get();
        const referrals = await db.collection('referrals')
            .where('referrerId', '==', uid)
            .get();
        
        const recentReferrals = await Promise.all(
            referrals.docs.slice(0, 10).map(async (ref) => {
                const referredUser = await db.collection('users').doc(ref.data().referredId).get();
                return {
                    name: referredUser.data()?.name || 'User',
                    joinedAt: formatDate(ref.data().createdAt),
                    bonus: ref.data().bonusGiven
                };
            })
        );
        
        res.json({
            success: true,
            totalReferrals: userDoc.data()?.totalReferrals || 0,
            totalEarnings: userDoc.data()?.totalReferralEarnings || 0,
            referralCode: userDoc.data()?.referralCode,
            recentReferrals
        });
    } catch (error) {
        console.error('Referral Stats Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== API: Seller Dashboard ==========
app.get('/api/seller/dashboard/:uid', async (req, res) => {
    try {
        const { uid } = req.params;
        
        const services = await db.collection('services').where('userId', '==', uid).get();
        const orders = await db.collection('orders').where('sellerId', '==', uid).get();
        
        // Get reviews for seller's services
        const serviceIds = services.docs.map(d => d.id);
        let reviews = [];
        if (serviceIds.length > 0) {
            const reviewsSnap = await db.collection('reviews')
                .where('serviceId', 'in', serviceIds.slice(0, 10))
                .get();
            reviews = reviewsSnap.docs;
        }
        
        const totalServices = services.size;
        const completedOrders = orders.docs.filter(d => d.data().status === 'completed').length;
        const pendingOrders = orders.docs.filter(d => d.data().status === 'reserved').length;
        const totalRevenue = orders.docs
            .filter(d => d.data().status === 'completed')
            .reduce((sum, d) => sum + d.data().servicePrice, 0);
        const avgRating = reviews.length > 0
            ? reviews.reduce((sum, d) => sum + d.data().rating, 0) / reviews.length
            : 0;
        
        const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
        const recentOrders = orders.docs.filter(d => {
            const createdAt = d.data().createdAt;
            return createdAt && createdAt.toDate() > weekAgo;
        }).length;
        
        res.json({
            success: true,
            stats: {
                totalServices,
                completedOrders,
                pendingOrders,
                totalRevenue: parseFloat(totalRevenue.toFixed(2)),
                avgRating: parseFloat(avgRating.toFixed(1)),
                totalReviews: reviews.length,
                recentOrders
            },
            topServices: services.docs
                .sort((a, b) => (b.data().views || 0) - (a.data().views || 0))
                .slice(0, 5)
                .map(d => ({ id: d.id, ...d.data() }))
        });
    } catch (error) {
        console.error('Seller Dashboard Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ========== Health Check ==========
app.get('/health', (req, res) => {
    res.json({ 
        status: 'healthy', 
        timestamp: new Date().toISOString(),
        uptime: process.uptime(),
        version: '3.0.0'
    });
});

// ========== Serve Static Files ==========
app.use(express.static(__dirname));

// Catch-all for SPA
app.get('*', (req, res) => {
    res.sendFile(path.join(__dirname, 'index.html'));
});

// ========== Start Server ==========
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log('='.repeat(60));
    console.log('🚀 All Arab Services Server v3.0.0');
    console.log('='.repeat(60));
    console.log(`📡 Server running on port: ${PORT}`);
    console.log(`🔥 Firebase project: ${process.env.FIREBASE_PROJECT_ID}`);
    console.log(`✅ API ready at: http://localhost:${PORT}/api/`);
    console.log(`🌐 Web app at: http://localhost:${PORT}`);
    console.log('='.repeat(60));
});