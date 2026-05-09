const express = require('express');
const cors = require('cors');
const admin = require('firebase-admin');
const app = express();
app.use(cors());
app.use(express.json({ limit: '10mb' }));

// 1. تهيئة Firebase Admin - ضع ملف serviceAccountKey.json في Render
const serviceAccount = JSON.parse(process.env.FIREBASE_SERVICE_ACCOUNT);
admin.initializeApp({
    credential: admin.credential.cert(serviceAccount),
    storageBucket: process.env.FIREBASE_STORAGE_BUCKET
});

const db = admin.firestore();
const storage = admin.storage().bucket();
const messaging = admin.messaging();

// ======================== 2. نظام الإشعارات الشامل ========================
// هذا النظام يشتغل مع أي وظيفة: طلب، بلاغ، شراء، تحديث، إلخ
async function sendNotification({ userId, type, title, body, data = {} }) {
    try {
        // 1. حفظ الإشعار في قاعدة البيانات
        const notifRef = db.collection('notifications').doc();
        await notifRef.set({
            id: notifRef.id,
            userId: userId,
            type: type, // order, report, purchase, system, custom
            title: title,
            body: body,
            data: data,
            read: false,
            createdAt: admin.firestore.FieldValue.serverTimestamp()
        });

        // 2. جلب FCM Token للمستخدم
        const userDoc = await db.collection('users').doc(userId).get();
        const fcmToken = userDoc.data()?.fcmToken;

        // 3. إرسال Push Notification لو عنده توكن
        if (fcmToken) {
            await messaging.send({
                token: fcmToken,
                notification: { title, body },
                data: {...data, type, notifId: notifRef.id },
                android: { priority: 'high' }
            });
        }

        return { success: true, notifId: notifRef.id };
    } catch (error) {
        console.error('Notification Error:', error);
        return { success: false, error: error.message };
    }
}

// ======================== 3. API: إنشاء خدمة جديدة ========================
app.post('/api/services/create', async (req, res) => {
    try {
        const { uid, serviceData, imageBase64 } = req.body;

        // تحقق من التوكن
        const userDoc = await db.collection('users').doc(uid).get();
        if (!userDoc.exists) return res.status(401).json({ error: 'Unauthorized' });

        const user = userDoc.data();

        // تحقق من الحد اليومي: 3 خدمات فقط
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        const todayServices = await db.collection('services')
           .where('userId', '==', uid)
           .where('createdAt', '>=', today)
           .get();

        if (todayServices.size >= 3) {
            return res.status(429).json({ error: 'تم تجاوز الحد اليومي 3 خدمات' });
        }

        // رفع الصورة على Firebase Storage
        let imageUrl = '';
        if (imageBase64) {
            const buffer = Buffer.from(imageBase64.split(',')[1], 'base64');
            const fileName = `services/${uid}/${Date.now()}.jpg`;
            const file = storage.file(fileName);
            await file.save(buffer, { contentType: 'image/jpeg' });
            await file.makePublic();
            imageUrl = `https://storage.googleapis.com/${storage.name}/${fileName}`;
        }

        // حساب السعر النهائي
        const finalPrice = serviceData.discountPercent > 0
           ? serviceData.basePrice - (serviceData.basePrice * serviceData.discountPercent / 100)
            : serviceData.basePrice;

        // حفظ الخدمة
        const serviceRef = db.collection('services').doc();
        const newService = {
            id: serviceRef.id,
           ...serviceData,
            price: parseFloat(finalPrice.toFixed(2)),
            image: imageUrl,
            userId: uid,
            deviceId: user.deviceId,
            status: 'pending', // يحتاج موافقة مشرف
            views: 0,
            createdAt: admin.firestore.FieldValue.serverTimestamp()
        };

        await serviceRef.set(newService);

        // إضافة نقاط للمستخدم
        await db.collection('users').doc(uid).update({
            points: admin.firestore.FieldValue.increment(10)
        });

        // إشعار للمستخدم
        await sendNotification({
            userId: uid,
            type: 'service',
            title: '✅ تم إنشاء الخدمة',
            body: `خدمتك "${serviceData.productName}" قيد المراجعة +10 نقاط`,
            data: { serviceId: serviceRef.id }
        });

        // إشعار للمشرفين
        const admins = await db.collection('users').where('role', '==', 'admin').get();
        admins.forEach(async (adminDoc) => {
            await sendNotification({
                userId: adminDoc.id,
                type: 'admin',
                title: '🆕 خدمة جديدة للمراجعة',
                body: `${serviceData.establishment} - ${serviceData.productName}`,
                data: { serviceId: serviceRef.id, action: 'review' }
            });
        });

        res.json({ success: true, serviceId: serviceRef.id, service: newService });

    } catch (error) {
        console.error('Create Service Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ======================== 4. API: نظام الطلبات الشامل ========================
app.post('/api/orders/create', async (req, res) => {
    try {
        const { uid, serviceId, quantity = 1, notes } = req.body;

        const serviceDoc = await db.collection('services').doc(serviceId).get();
        if (!serviceDoc.exists) return res.status(404).json({ error: 'Service not found' });

        const service = serviceDoc.data();
        const totalPrice = service.price * quantity;

        // إنشاء الطلب
        const orderRef = db.collection('orders').doc();
        const order = {
            id: orderRef.id,
            userId: uid,
            serviceId: serviceId,
            sellerId: service.userId,
            quantity: quantity,
            unitPrice: service.price,
            totalPrice: totalPrice,
            currency: service.currency,
            status: 'pending', // pending, confirmed, completed, cancelled
            notes: notes || '',
            createdAt: admin.firestore.FieldValue.serverTimestamp()
        };

        await orderRef.set(order);

        // إشعار للمشتري
        await sendNotification({
            userId: uid,
            type: 'order',
            title: '🛒 تم إنشاء طلبك',
            body: `طلب ${service.productName} - ${totalPrice} ${service.currency}`,
            data: { orderId: orderRef.id, status: 'pending' }
        });

        // إشعار للبائع
        await sendNotification({
            userId: service.userId,
            type: 'order',
            title: '📦 طلب جديد!',
            body: `طلب جديد على ${service.productName} بقيمة ${totalPrice}`,
            data: { orderId: orderRef.id, action: 'view_order' }
        });

        res.json({ success: true, orderId: orderRef.id, order });

    } catch (error) {
        console.error('Create Order Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ======================== 5. API: نظام البلاغات ========================
app.post('/api/reports/create', async (req, res) => {
    try {
        const { uid, targetType, targetId, reason, description } = req.body;

        const reportRef = db.collection('reports').doc();
        const report = {
            id: reportRef.id,
            reporterId: uid,
            targetType: targetType, // service, user, order
            targetId: targetId,
            reason: reason,
            description: description,
            status: 'pending', // pending, reviewed, resolved
            createdAt: admin.firestore.FieldValue.serverTimestamp()
        };

        await reportRef.set(report);

        // إشعار للمبلغ
        await sendNotification({
            userId: uid,
            type: 'report',
            title: '✅ تم استلام بلاغك',
            body: 'سيتم مراجعة البلاغ خلال 24 ساعة',
            data: { reportId: reportRef.id }
        });

        // إشعار للمشرفين
        const admins = await db.collection('users').where('role', '==', 'admin').get();
        admins.forEach(async (adminDoc) => {
            await sendNotification({
                userId: adminDoc.id,
                type: 'admin',
                title: '🚨 بلاغ جديد',
                body: `بلاغ على ${targetType}: ${reason}`,
                data: { reportId: reportRef.id, action: 'review_report' }
            });
        });

        res.json({ success: true, reportId: reportRef.id });

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ======================== 6. API: جلب الإشعارات ========================
app.get('/api/notifications/:uid', async (req, res) => {
    try {
        const { uid } = req.params;
        const snapshot = await db.collection('notifications')
           .where('userId', '==', uid)
           .orderBy('createdAt', 'desc')
           .limit(50)
           .get();

        const notifications = snapshot.docs.map(doc => doc.data());
        res.json({ success: true, notifications });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ======================== 7. API: تحديث حالة الطلب ========================
app.put('/api/orders/:orderId/status', async (req, res) => {
    try {
        const { orderId } = req.params;
        const { status, uid } = req.body;

        const orderDoc = await db.collection('orders').doc(orderId).get();
        if (!orderDoc.exists) return res.status(404).json({ error: 'Order not found' });

        const order = orderDoc.data();
        await db.collection('orders').doc(orderId).update({ status });

        // إشعار للطرفين
        await sendNotification({
            userId: order.userId,
            type: 'order',
            title: '📦 تحديث طلبك',
            body: `حالة الطلب: ${getStatusText(status)}`,
            data: { orderId, status }
        });

        await sendNotification({
            userId: order.sellerId,
            type: 'order',
            title: '📦 تحديث طلب',
            body: `تم تحديث حالة الطلب إلى: ${getStatusText(status)}`,
            data: { orderId, status }
        });

        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

function getStatusText(status) {
    const map = {
        pending: 'قيد الانتظار',
        confirmed: 'تم التأكيد',
        completed: 'مكتمل',
        cancelled: 'ملغي'
    };
    return map[status] || status;
}

// ======================== 8. API: التحقق من التحديثات ========================
app.get('/api/app/version', async (req, res) => {
    const versionDoc = await db.collection('config').doc('app_version').get();
    res.json({ version: versionDoc.data()?.version || '1.0.0' });
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log(`Server running on port ${PORT}`));

// في server.js أضف:

// جلب الإشعارات
app.get('/api/notifications/:uid', async (req, res) => {
    try {
        const snapshot = await db.collection('notifications')
           .where('userId', '==', req.params.uid)
           .orderBy('createdAt', 'desc')
           .limit(50)
           .get();
        const notifications = snapshot.docs.map(doc => ({ id: doc.id,...doc.data() }));
        res.json({ success: true, notifications });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// تحديد إشعار كمقروء
app.put('/api/notifications/:notifId/read', async (req, res) => {
    await db.collection('notifications').doc(req.params.notifId).update({ read: true });
    res.json({ success: true });
});

// تحديد الكل كمقروء
app.put('/api/notifications/mark-all-read', async (req, res) => {
    const { uid } = req.body;
    const batch = db.batch();
    const snapshot = await db.collection('notifications')
       .where('userId', '==', uid)
       .where('read', '==', false)
       .get();
    snapshot.docs.forEach(doc => batch.update(doc.ref, { read: true }));
    await batch.commit();
    res.json({ success: true });
});

// جلب الطلبات
app.get('/api/orders/:uid', async (req, res) => {
    const snapshot = await db.collection('orders')
       .where('userId', '==', req.params.uid)
       .orderBy('createdAt', 'desc')
       .get();
    const orders = await Promise.all(snapshot.docs.map(async (doc) => {
        const order = doc.data();
        const serviceDoc = await db.collection('services').doc(order.serviceId).get();
        return {...order, serviceName: serviceDoc.data()?.productName || 'غير معروف' };
    }));
    res.json(orders);
});

// تفاصيل الطلب
app.get('/api/orders/:orderId/details', async (req, res) => {
    const doc = await db.collection('orders').doc(req.params.orderId).get();
    const order = doc.data();
    const serviceDoc = await db.collection('services').doc(order.serviceId).get();
    res.json({...order, serviceName: serviceDoc.data()?.productName });
});

// إنشاء تقييم
app.post('/api/reviews/create', async (req, res) => {
    const { uid, serviceId, orderId, rating, comment } = req.body;
    const reviewRef = db.collection('reviews').doc();
    await reviewRef.set({
        id: reviewRef.id,
        userId: uid, serviceId, orderId, rating, comment,
        createdAt: admin.firestore.FieldValue.serverTimestamp()
    });

    // تحديث متوسط تقييم الخدمة
    const reviewsSnap = await db.collection('reviews').where('serviceId', '==', serviceId).get();
    const avgRating = reviewsSnap.docs.reduce((sum, d) => sum + d.data().rating, 0) / reviewsSnap.size;
    await db.collection('services').doc(serviceId).update({
        avgRating: parseFloat(avgRating.toFixed(1)),
        reviewCount: reviewsSnap.size
    });

    res.json({ success: true });
});

// endpoints المشرف
app.get('/api/admin/services/pending', async (req, res) => {
    const snapshot = await db.collection('services').where('status', '==', 'pending').get();
    res.json(snapshot.docs.map(doc => doc.data()));
});

app.put('/api/admin/services/:serviceId/approve', async (req, res) => {
    const { serviceId } = req.params;
    await db.collection('services').doc(serviceId).update({ status: 'approved' });
    const service = await db.collection('services').doc(serviceId).get();
    await sendNotification({
        userId: service.data().userId,
        type: 'service',
        title: '✅ تمت الموافقة على خدمتك',
        body: `خدمة "${service.data().productName}" أصبحت متاحة الآن`,
        data: { serviceId }
    });
    res.json({ success: true });
});

app.put('/api/admin/services/:serviceId/reject', async (req, res) => {
    await db.collection('services').doc(req.params.serviceId).update({ status: 'rejected' });
    res.json({ success: true });
});

app.get('/api/admin/reports/pending', async (req, res) => {
    const snapshot = await db.collection('reports').where('status', '==', 'pending').get();
    res.json(snapshot.docs.map(doc => doc.data()));
});

app.put('/api/admin/reports/:reportId/resolve', async (req, res) => {
    await db.collection('reports').doc(req.params.reportId).update({ status: 'resolved' });
    res.json({ success: true });
});

app.get('/api/admin/stats', async (req, res) => {
    const [services, users, orders] = await Promise.all([
        db.collection('services').count().get(),
        db.collection('users').count().get(),
        db.collection('orders').count().get()
    ]);
    res.json({
        totalServices: services.data().count,
        totalUsers: users.data().count,
        totalOrders: orders.data().count
    });
});

// ======================== 9. نظام النقاط الموحد ========================
async function updateWallet(uid, amount, type, refType, refId, description) {
    const userRef = db.collection('users').doc(uid);

    return await db.runTransaction(async (t) => {
        const userDoc = await t.get(userRef);
        if (!userDoc.exists) throw new Error('User not found');

        const currentPoints = userDoc.data().points || 0;
        const newBalance = currentPoints + amount;

        if (newBalance < 0) throw new Error('رصيد النقاط غير كافي');
        if (userDoc.data().walletFrozen) throw new Error('المحفظة مجمدة');

        t.update(userRef, {
            points: newBalance,
            totalEarned: admin.firestore.FieldValue.increment(amount > 0? amount : 0),
            totalSpent: admin.firestore.FieldValue.increment(amount < 0? Math.abs(amount) : 0)
        });

        const txnRef = db.collection('wallet_transactions').doc();
        t.set(txnRef, {
            id: txnRef.id,
            userId: uid,
            type, // earn, spend, refund, penalty, bonus
            amount,
            balanceBefore: currentPoints,
            balanceAfter: newBalance,
            refType, // referral, order, coupon, service, admin
            refId,
            description,
            deviceId: userDoc.data().deviceId,
            createdAt: admin.firestore.FieldValue.serverTimestamp(),
            status: 'completed'
        });

        return { newBalance, txnId: txnRef.id };
    });
}

// ======================== 10. نظام الكوبونات الشامل ========================
app.post('/api/coupons/validate-use', async (req, res) => {
    try {
        const { uid, code, context } = req.body;
        // context = { type: 'order'|'upgrade'|'referral'|'points', targetId: 'xxx', amount: 100 }

        const couponSnap = await db.collection('coupons').where('code', '==', code).get();
        if (couponSnap.empty) return res.status(404).json({ error: 'كوبون غير صحيح' });

        const coupon = couponSnap.docs[0].data();
        const couponId = couponSnap.docs[0].id;

        // 1. تحققات عامة
        if (!coupon.isActive) return res.status(400).json({ error: 'كوبون معطل' });
        if (coupon.expiry && coupon.expiry.toDate() < new Date()) return res.status(400).json({ error: 'كوبون منتهي' });
        if (coupon.usedBy?.includes(uid)) return res.status(400).json({ error: 'استخدمت هذا الكوبون مسبقاً' });
        if (coupon.usedCount >= coupon.maxUses) return res.status(400).json({ error: 'انتهت صلاحية الكوبون' });

        // 2. تحققات حسب نوع الكوبون
        let result = { valid: true, action: null, value: 0 };

        switch (coupon.type) {
            case 'points': // كوبون استلام نقاط
                result.action = 'add_points';
                result.value = coupon.value;
                await updateWallet(uid, coupon.value, 'earn', 'coupon', code, `كوبون نقاط ${code}`);
                break;

            case 'percent_discount': // خصم نسبة من طلب
                if (context.type!== 'order') return res.status(400).json({ error: 'الكوبون للطلبات فقط' });
                if (context.amount < coupon.minOrderValue) return res.status(400).json({ error: `الطلب أقل من ${coupon.minOrderValue}` });
                result.action = 'discount';
                result.value = context.amount * (coupon.value / 100);
                break;

            case 'fixed_discount': // خصم مبلغ ثابت
                if (context.type!== 'order') return res.status(400).json({ error: 'الكوبون للطلبات فقط' });
                result.action = 'discount';
                result.value = coupon.value;
                break;

            case 'upgrade_personal': // ترقية حساب شخصي
                result.action = 'upgrade_role';
                result.value = 'premium_user';
                await db.collection('users').doc(uid).update({ role: 'premium_user' });
                await sendNotification({
                    userId: uid, type: 'system',
                    title: '👑 تمت ترقية حسابك',
                    body: 'أصبحت عضو مميز الآن',
                    data: { coupon: code }
                });
                break;

            case 'upgrade_business': // ترقية حساب منشأة
                result.action = 'upgrade_role';
                result.value = 'premium_business';
                await db.collection('users').doc(uid).update({ role: 'premium_business' });
                await sendNotification({
                    userId: uid, type: 'system',
                    title: '🏢 تمت ترقية منشأتك',
                    body: 'منشأتك الآن مميزة',
                    data: { coupon: code }
                });
                break;

            case 'referral_bonus': // مكافأة إحالة إضافية
                result.action = 'add_points';
                result.value = coupon.value;
                await updateWallet(uid, coupon.value, 'earn', 'coupon', code, `مكافأة إحالة ${code}`);
                break;

            case 'confirm_purchase': // تأكيد شراء - يرجع 5% من النقاط المخصومة
                if (context.type!== 'order') return res.status(400).json({ error: 'كوبون تأكيد الشراء للطلبات فقط' });
                const cashback = context.amount * 0.05;
                result.action = 'add_points';
                result.value = cashback;
                await updateWallet(uid, cashback, 'earn', 'coupon', code, `كاش باك تأكيد شراء`);
                break;

            case 'product_update': // تحديث معلومات منتج
                result.action = 'allow_update';
                result.value = context.targetId; // serviceId
                break;

            default:
                return res.status(400).json({ error: 'نوع كوبون غير معروف' });
        }

        // 3. تسجيل استخدام الكوبون
        await db.collection('coupons').doc(couponId).update({
            usedCount: admin.firestore.FieldValue.increment(1),
            usedBy: admin.firestore.FieldValue.arrayUnion(uid),
            lastUsed: admin.firestore.FieldValue.serverTimestamp()
        });

        // 4. سجل العملية
        await logAction(uid, 'use_coupon', 'coupon', code, { type: coupon.type, value: result.value }, 'success');

        res.json({ success: true,...result });

    } catch (error) {
        console.error('Coupon Error:', error);
        res.status(500).json({ error: error.message });
    }
});

// ======================== 11. حجز منتج - خصم 15% نقاط ========================
app.post('/api/orders/reserve', async (req, res) => {
    try {
        const { uid, serviceId, couponCode } = req.body;

        const [userDoc, serviceDoc] = await Promise.all([
            db.collection('users').doc(uid).get(),
            db.collection('services').doc(serviceId).get()
        ]);

        if (!serviceDoc.exists) return res.status(404).json({ error: 'الخدمة غير موجودة' });

        const service = serviceDoc.data();
        const user = userDoc.data();
        const basePrice = parseFloat(service.price);

        // 1. حساب العربون 15% كنقاط: كل 1 ريال = 10 نقاط
        let depositPoints = Math.ceil(basePrice * 0.15 * 10);
        let finalDeposit = depositPoints;
        let discountApplied = 0;

        // 2. تطبيق كوبون لو موجود
        if (couponCode) {
            const couponResult = await validateCouponInternal(uid, couponCode, {
                type: 'order',
                amount: basePrice,
                targetId: serviceId
            });
            if (couponResult.valid && couponResult.action === 'discount') {
                discountApplied = couponResult.value;
                // الخصم يقلل من العربون
                finalDeposit = Math.ceil((basePrice - discountApplied) * 0.15 * 10);
            }
        }

        // 3. خصم النقاط من المحفظة
        await updateWallet(uid, -finalDeposit, 'spend', 'order', serviceId,
            `عربون حجز ${service.productName} - خصم ${discountApplied.toFixed(2)}`);

        // 4. إنشاء الطلب
        const orderRef = db.collection('orders').doc();
        const order = {
            id: orderRef.id,
            buyerId: uid,
            buyerName: user.name,
            buyerPhone: user.phone,
            sellerId: service.userId,
            serviceId: serviceId,
            serviceName: service.productName,
            servicePrice: basePrice,
            currency: service.currency,
            depositPoints: finalDeposit,
            discountApplied: discountApplied,
            couponUsed: couponCode || null,
            status: 'reserved', // محجوز مؤقتاً
            expiresAt: new Date(Date.now() + 24 * 60 * 60 * 1000), // ينتهي بعد 24 ساعة
            createdAt: admin.firestore.FieldValue.serverTimestamp()
        };
        await orderRef.set(order);

        // 5. إشعار للبائع
        await sendNotification({
            userId: service.userId,
            type: 'order',
            title: '🔔 حجز جديد!',
            body: `${user.name} حجز ${service.productName}. العربون: ${finalDeposit} نقطة`,
            data: { orderId: orderRef.id, action: 'view_order', buyerPhone: user.phone }
        });

        // 6. إشعار للمشتري
        await sendNotification({
            userId: uid,
            type: 'order',
            title: '✅ تم الحجز بنجاح',
            body: `تم خصم ${finalDeposit} نقطة كعربون. تواصل مع البائع لإتمام الشراء`,
            data: { orderId: orderRef.id, sellerPhone: service.contact }
        });

        await logAction(uid, 'reserve_service', 'order', orderRef.id, { depositPoints: finalDeposit }, 'success');

        res.json({
            success: true,
            orderId: orderRef.id,
            depositPoints: finalDeposit,
            sellerContact: service.contact,
            whatsappMsg: formatWhatsAppOrder(order, user, service)
        });

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

function formatWhatsAppOrder(order, buyer, service) {
    return `🏢 *طلب حجز جديد*
📦 المنتج: ${service.productName}
🆔 رقم الطلب: ${order.id}
💰 السعر: ${service.price} ${service.currency}
💎 العربون المدفوع: ${order.depositPoints} نقطة

👤 *بيانات المشتري*
الاسم: ${buyer.name}
الجوال: ${buyer.phone}

الرجاء التواصل لإتمام الشراء. الدفع الحقيقي خارج التطبيق.`;
}

// ======================== 12. التسجيل بمعرف إحالة ========================
app.post('/api/auth/register-with-referral', async (req, res) => {
    try {
        const { uid, referralCode } = req.body;

        if (!referralCode) return res.json({ success: true, bonus: 0 });

        // البحث عن صاحب الكود
        const referrerSnap = await db.collection('users')
           .where('referralCode', '==', referralCode.toUpperCase())
           .limit(1).get();

        if (referrerSnap.empty) return res.json({ success: true, bonus: 0 });

        const referrer = referrerSnap.docs[0];
        const bonusPoints = 50;

        // إضافة نقاط للمحيل
        await updateWallet(referrer.id, bonusPoints, 'earn', 'referral', uid,
            `مكافأة إحالة مستخدم جديد`);

        // إشعار للمحيل
        await sendNotification({
            userId: referrer.id,
            type: 'referral',
            title: '🎉 مكافأة إحالة!',
            body: `تم إضافة ${bonusPoints} نقطة لرصيدك عبر رابط الإحالة`,
            data: { newUserId: uid }
        });

        // تحديث المستخدم الجديد
        await db.collection('users').doc(uid).update({ referredBy: referrer.id });

        res.json({ success: true, bonus: bonusPoints, referrerName: referrer.data().name });

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ======================== 13. ترقية حساب من المشرف عبر تليجرام ========================
app.post('/api/admin/upgrade-user', async (req, res) => {
    try {
        const { adminUid, targetUid, newRole, reason } = req.body;

        // تحقق من صلاحية المشرف
        const adminDoc = await db.collection('users').doc(adminUid).get();
        if (adminDoc.data().role!== 'admin') return res.status(403).json({ error: 'غير مصرح' });

        await db.collection('users').doc(targetUid).update({
            role: newRole,
            upgradedAt: admin.firestore.FieldValue.serverTimestamp(),
            upgradedBy: adminUid
        });

        // إشعار للمستخدم
        await sendNotification({
            userId: targetUid,
            type: 'system',
            title: '👑 تمت ترقية حسابك',
            body: `تم ترقيتك إلى ${newRole === 'premium_user'? 'عضو مميز' : 'منشأة مميزة'}`,
            data: { reason }
        });

        await logAction(adminUid, 'upgrade_user', 'user', targetUid, { newRole, reason }, 'success');

        res.json({ success: true });

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// دالة مساعدة للتحقق من الكوبون داخلياً
async function validateCouponInternal(uid, code, context) {
    // نفس منطق /api/coupons/validate-use لكن بدون response
    // اختصاراً: استدعاء مباشر للمنطق
    return { valid: true, action: 'discount', value: 0 }; // للتطبيق الحقيقي انسخ المنطق من فوق
}

// ======================== 14. نظام التقييمات الكامل ========================
app.post('/api/reviews/create', async (req, res) => {
    try {
        const { uid, serviceId, orderId, rating, comment, images } = req.body;

        // تحقق أن الطلب مكتمل وأن المستخدم هو المشتري
        const orderDoc = await db.collection('orders').doc(orderId).get();
        if (!orderDoc.exists) return res.status(404).json({ error: 'الطلب غير موجود' });
        if (orderDoc.data().buyerId !== uid) return res.status(403).json({ error: 'غير مصرح' });
        if (orderDoc.data().status !== 'completed') return res.status(400).json({ error: 'يجب إتمام الشراء أولاً' });

        // تحقق من عدم التقييم مسبقاً
        const existingReview = await db.collection('reviews')
           .where('orderId', '==', orderId).limit(1).get();
        if (!existingReview.empty) return res.status(400).json({ error: 'قيمت هذا الطلب مسبقاً' });

        const reviewRef = db.collection('reviews').doc();
        const review = {
            id: reviewRef.id,
            userId: uid,
            serviceId,
            orderId,
            rating: Math.min(5, Math.max(1, rating)), // 1-5 فقط
            comment: comment || '',
            images: images || [],
            helpful: 0,
            reported: false,
            createdAt: admin.firestore.FieldValue.serverTimestamp()
        };

        await reviewRef.set(review);

        // تحديث متوسط تقييم الخدمة
        const reviewsSnap = await db.collection('reviews').where('serviceId', '==', serviceId).get();
        const avgRating = reviewsSnap.docs.reduce((sum, d) => sum + d.data().rating, 0) / reviewsSnap.size;

        await db.collection('services').doc(serviceId).update({
            avgRating: parseFloat(avgRating.toFixed(1)),
            reviewCount: reviewsSnap.size,
            lastReviewAt: admin.firestore.FieldValue.serverTimestamp()
        });

        // مكافأة نقاط للتقييم
        await updateWallet(uid, 5, 'earn', 'review', reviewRef.id, 'مكافأة تقييم منتج');

        // إشعار للبائع
        const serviceDoc = await db.collection('services').doc(serviceId).get();
        await sendNotification({
            userId: serviceDoc.data().userId,
            type: 'review',
            title: '⭐ تقييم جديد',
            body: `تم تقييم ${serviceDoc.data().productName} بـ ${rating} نجوم`,
            data: { reviewId: reviewRef.id, serviceId }
        });

        await logAction(uid, 'create_review', 'review', reviewRef.id, { rating, serviceId }, 'success');
        res.json({ success: true, reviewId: reviewRef.id });

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// جلب تقييمات خدمة مع فلترة
app.get('/api/reviews/:serviceId', async (req, res) => {
    try {
        const { serviceId } = req.params;
        const { rating, sort = 'newest' } = req.query; // rating=5, sort=newest|helpful

        let query = db.collection('reviews').where('serviceId', '==', serviceId);

        if (rating) query = query.where('rating', '==', parseInt(rating));

        if (sort === 'helpful') query = query.orderBy('helpful', 'desc');
        else query = query.orderBy('createdAt', 'desc');

        const snapshot = await query.limit(50).get();

        // جلب أسماء المستخدمين
        const reviews = await Promise.all(snapshot.docs.map(async (doc) => {
            const review = doc.data();
            const userDoc = await db.collection('users').doc(review.userId).get();
            return {
               ...review,
                userName: userDoc.data()?.name || 'مستخدم',
                userAvatar: userDoc.data()?.avatar || null
            };
        }));

        res.json({ success: true, reviews });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ======================== 15. لوحة المشرف المتقدمة ========================
app.get('/api/admin/dashboard/stats', async (req, res) => {
    try {
        const { adminUid } = req.query;
        const adminDoc = await db.collection('users').doc(adminUid).get();
        if (adminDoc.data().role !== 'admin') return res.status(403).json({ error: 'غير مصرح' });

        const [services, users, orders, transactions, reports] = await Promise.all([
            db.collection('services').count().get(),
            db.collection('users').count().get(),
            db.collection('orders').count().get(),
            db.collection('wallet_transactions').count().get(),
            db.collection('reports').where('status', '==', 'pending').count().get()
        ]);

        // إحصائيات اليوم
        const today = new Date();
        today.setHours(0, 0, 0, 0);

        const [todayOrders, todayUsers, todayRevenue] = await Promise.all([
            db.collection('orders').where('createdAt', '>=', today).count().get(),
            db.collection('users').where('createdAt', '>=', today).count().get(),
            db.collection('wallet_transactions')
               .where('type', '==', 'spend')
               .where('createdAt', '>=', today)
               .get()
        ]);

        const revenue = todayRevenue.docs.reduce((sum, doc) => sum + Math.abs(doc.data().amount), 0);

        res.json({
            total: {
                services: services.data().count,
                users: users.data().count,
                orders: orders.data().count,
                transactions: transactions.data().count,
                pendingReports: reports.data().count
            },
            today: {
                orders: todayOrders.data().count,
                users: todayUsers.data().count,
                revenue: revenue
            }
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// فلترة الخدمات للمشرف
app.get('/api/admin/services/filter', async (req, res) => {
    try {
        const { status, category, search, startDate, endDate } = req.query;
        let query = db.collection('services');

        if (status) query = query.where('status', '==', status);
        if (category) query = query.where('category_id', '==', category);
        if (startDate) query = query.where('createdAt', '>=', new Date(startDate));
        if (endDate) query = query.where('createdAt', '<=', new Date(endDate));

        query = query.orderBy('createdAt', 'desc').limit(100);
        const snapshot = await query.get();
        let services = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));

        // فلترة نصية محلية
        if (search) {
            const s = search.toLowerCase();
            services = services.filter(svc =>
                svc.productName.toLowerCase().includes(s) ||
                svc.establishment.toLowerCase().includes(s)
            );
        }

        res.json({ success: true, services });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// حظر/فك حظر مستخدم
app.put('/api/admin/users/:uid/ban', async (req, res) => {
    try {
        const { adminUid, reason, banned } = req.body;

        await db.collection('users').doc(req.params.uid).update({
            walletFrozen: banned,
            banned: banned,
            banReason: reason,
            bannedAt: banned ? admin.firestore.FieldValue.serverTimestamp() : null,
            bannedBy: banned ? adminUid : null
        });

        await sendNotification({
            userId: req.params.uid,
            type: 'system',
            title: banned ? '🚫 تم حظر حسابك' : '✅ تم فك الحظر',
            body: banned ? `السبب: ${reason}` : 'يمكنك استخدام التطبيق الآن',
            data: { banned, reason }
        });

        await logAction(adminUid, banned ? 'ban_user' : 'unban_user', 'user', req.params.uid, { reason }, 'success');
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ======================== 16. التقارير الشاملة ========================
app.get('/api/admin/reports/export', async (req, res) => {
    try {
        const { type, startDate, endDate } = req.query;
        let data = [];

        switch (type) {
            case 'orders':
                const ordersSnap = await db.collection('orders')
                   .where('createdAt', '>=', new Date(startDate))
                   .where('createdAt', '<=', new Date(endDate))
                   .get();
                data = ordersSnap.docs.map(d => d.data());
                break;

            case 'transactions':
                const txSnap = await db.collection('wallet_transactions')
                   .where('createdAt', '>=', new Date(startDate))
                   .where('createdAt', '<=', new Date(endDate))
                   .get();
                data = txSnap.docs.map(d => d.data());
                break;

            case 'users':
                const usersSnap = await db.collection('users')
                   .where('createdAt', '>=', new Date(startDate))
                   .where('createdAt', '<=', new Date(endDate))
                   .get();
                data = usersSnap.docs.map(d => d.data());
                break;
        }

        res.json({ success: true, data, count: data.length });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ======================== 17. معالجة طلبات الترقية للمشرف ========================
app.get('/api/admin/upgrade-requests', async (req, res) => {
    try {
        const { adminUid } = req.query;
        const adminDoc = await db.collection('users').doc(adminUid).get();
        if (adminDoc.data().role !== 'admin') return res.status(403).json({ error: 'غير مصرح' });

        const snapshot = await db.collection('upgrade_requests')
           .where('status', '==', 'pending')
           .orderBy('createdAt', 'desc')
           .get();

        const requests = snapshot.docs.map(doc => ({ id: doc.id, ...doc.data() }));
        res.json({ success: true, requests });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

app.put('/api/admin/upgrade-requests/:requestId/approve', async (req, res) => {
    try {
        const { adminUid } = req.body;
        const requestId = req.params.requestId;

        const reqDoc = await db.collection('upgrade_requests').doc(requestId).get();
        if (!reqDoc.exists) return res.status(404).json({ error: 'الطلب غير موجود' });

        const request = reqDoc.data();

        // ترقية المستخدم
        await db.collection('users').doc(request.userId).update({
            role: request.requestedRole,
            upgradedAt: admin.firestore.FieldValue.serverTimestamp(),
            upgradedBy: adminUid
        });

        // تحديث حالة الطلب
        await db.collection('upgrade_requests').doc(requestId).update({
            status: 'approved',
            approvedAt: admin.firestore.FieldValue.serverTimestamp(),
            approvedBy: adminUid
        });

        // إشعار للمستخدم - يوصله فوراً عبر onSnapshot
        await sendNotification({
            userId: request.userId,
            type: 'system',
            title: '🎉 تمت ترقية حسابك!',
            body: `تمت ترقيتك إلى ${request.requestedRole === 'premium_user' ? 'عضو مميز' : 'منشأة مميزة'}`,
            data: { newRole: request.requestedRole }
        });

        await logAction(adminUid, 'approve_upgrade', 'user', request.userId, { requestedRole: request.requestedRole }, 'success');
        res.json({ success: true });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ======================== 18. نظام الإحالات المتقدم ========================
app.post('/api/referral/track', async (req, res) => {
    try {
        const { newUserId, referralCode } = req.body;

        // البحث عن المحيل
        const referrerSnap = await db.collection('users')
          .where('referralCode', '==', referralCode.toUpperCase())
          .limit(1).get();

        if (referrerSnap.empty) return res.json({ success: false, reason: 'invalid_code' });

        const referrerDoc = referrerSnap.docs[0];
        const referrerId = referrerDoc.id;

        // منع الإحالة الذاتية
        if (referrerId === newUserId) return res.json({ success: false, reason: 'self_referral' });

        // تحقق من عدم الإحالة مسبقاً
        const existingRef = await db.collection('referrals')
          .where('referredId', '==', newUserId).limit(1).get();
        if (!existingRef.empty) return res.json({ success: false, reason: 'already_referred' });

        const bonusPoints = 50;

        // تسجيل الإحالة
        await db.collection('referrals').add({
            referrerId: referrerId,
            referredId: newUserId,
            referralCode: referralCode,
            bonusGiven: bonusPoints,
            status: 'active',
            createdAt: admin.firestore.FieldValue.serverTimestamp()
        });

        // إضافة نقاط للمحيل
        await updateWallet(referrerId, bonusPoints, 'earn', 'referral', newUserId,
            `مكافأة إحالة مستخدم جديد`);

        // تحديث المستخدم الجديد
        await db.collection('users').doc(newUserId).update({
            referredBy: referrerId,
            referralBonusReceived: true
        });

        // تحديث إحصائيات المحيل
        await db.collection('users').doc(referrerId).update({
            totalReferrals: admin.firestore.FieldValue.increment(1),
            totalReferralEarnings: admin.firestore.FieldValue.increment(bonusPoints)
        });

        // إشعار للمحيل
        await sendNotification({
            userId: referrerId,
            type: 'referral',
            title: '🎉 مكافأة إحالة جديدة!',
            body: `شخص جديد سجل بكودك! +${bonusPoints} نقطة`,
            data: { newUserId, bonus: bonusPoints }
        });

        // إشعار للمشرف على التليجرام
        await notifyAdminTelegram(`🆕 إحالة جديدة\nالمحيل: ${referrerDoc.data().name}\nالمكافأة: ${bonusPoints} نقطة`);

        res.json({ success: true, bonus: bonusPoints, referrerName: referrerDoc.data().name });

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// إحصائيات الإحالات
app.get('/api/referral/stats/:uid', async (req, res) => {
    try {
        const { uid } = req.params;

        const [referralsSnap, userDoc] = await Promise.all([
            db.collection('referrals').where('referrerId', '==', uid).get(),
            db.collection('users').doc(uid).get()
        ]);

        const referrals = referralsSnap.docs.map(d => d.data());
        const userData = userDoc.data();

        // جلب أسماء المحالين
        const referredUsers = await Promise.all(
            referrals.slice(0, 20).map(async (ref) => {
                const userDoc = await db.collection('users').doc(ref.referredId).get();
                return {
                    name: userDoc.data()?.name || 'مستخدم',
                    joinedAt: ref.createdAt,
                    bonus: ref.bonusGiven
                };
            })
        );

        res.json({
            success: true,
            totalReferrals: userData.totalReferrals || 0,
            totalEarnings: userData.totalReferralEarnings || 0,
            referralCode: userData.referralCode,
            recentReferrals: referredUsers
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ======================== 19. إشعارات التليجرام للمشرف ========================
const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN; // من Render Environment
const TELEGRAM_ADMIN_CHAT_ID = process.env.TELEGRAM_ADMIN_CHAT_ID;

async function notifyAdminTelegram(message) {
    if (!TELEGRAM_BOT_TOKEN ||!TELEGRAM_ADMIN_CHAT_ID) return;

    try {
        const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;
        await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chat_id: TELEGRAM_ADMIN_CHAT_ID,
                text: message,
                parse_mode: 'HTML'
            })
        });
    } catch (error) {
        console.error('Telegram Error:', error);
    }
}

// إشعار عند طلب ترقية جديد
app.post('/api/admin/upgrade-request-webhook', async (req, res) => {
    const { userId, userName, currentRole, requestedRole } = req.body;

    const msg = `🔔 <b>طلب ترقية جديد</b>\n\n` +
                `👤 الاسم: ${userName}\n` +
                `📱 ID: <code>${userId}</code>\n` +
                `من: ${currentRole}\n` +
                `إلى: ${requestedRole}\n\n` +
                `/approve_${userId} - موافقة\n` +
                `/reject_${userId} - رفض`;

    await notifyAdminTelegram(msg);
    res.json({ success: true });
});

// إشعار عند بلاغ جديد
app.post('/api/admin/report-webhook', async (req, res) => {
    const { reportId, reason, targetType } = req.body;

    const msg = `🚨 <b>بلاغ جديد</b>\n\n` +
                `النوع: ${targetType}\n` +
                `السبب: ${reason}\n` +
                `ID: <code>${reportId}</code>\n\n` +
                `/review_report_${reportId}`;

    await notifyAdminTelegram(msg);
    res.json({ success: true });
});

// ======================== 20. لوحة البائع - إحصائيات ========================
app.get('/api/seller/dashboard/:uid', async (req, res) => {
    try {
        const { uid } = req.params;

        const [services, orders, reviews] = await Promise.all([
            db.collection('services').where('userId', '==', uid).get(),
            db.collection('orders').where('sellerId', '==', uid).get(),
            db.collection('reviews').where('serviceId', 'in',
                (await db.collection('services').where('userId', '==', uid).get()).docs.map(d => d.id).slice(0, 10) || ['none']
            ).get()
        ]);

        const totalServices = services.size;
        const totalOrders = orders.size;
        const completedOrders = orders.docs.filter(d => d.data().status === 'completed').length;
        const pendingOrders = orders.docs.filter(d => d.data().status === 'reserved').length;

        const totalRevenue = orders.docs.reduce((sum, doc) => {
            const o = doc.data();
            return o.status === 'completed'? sum + o.servicePrice : sum;
        }, 0);

        const avgRating = reviews.docs.length > 0
          ? reviews.docs.reduce((sum, d) => sum + d.data().rating, 0) / reviews.docs.length
            : 0;

        // إحصائيات آخر 7 أيام
        const weekAgo = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
        const recentOrders = orders.docs.filter(d => d.data().createdAt.toDate() > weekAgo).length;

        res.json({
            success: true,
            stats: {
                totalServices,
                totalOrders,
                completedOrders,
                pendingOrders,
                totalRevenue: parseFloat(totalRevenue.toFixed(2)),
                avgRating: parseFloat(avgRating.toFixed(1)),
                totalReviews: reviews.size,
                recentOrders
            },
            topServices: services.docs
              .sort((a, b) => (b.data().views || 0) - (a.data().views || 0))
              .slice(0, 5)
              .map(d => ({ id: d.id,...d.data() }))
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

// ======================== 21. نظام البلاغات المتقدم + مكافحة الغش ========================
app.post('/api/reports/create', async (req, res) => {
    try {
        const { uid, targetType, targetId, reason, description, evidence } = req.body;

        // 1. منع البلاغات المتكررة
        const recentReport = await db.collection('reports')
          .where('reporterId', '==', uid)
          .where('targetId', '==', targetId)
          .where('createdAt', '>', new Date(Date.now() - 24 * 60 * 60 * 1000))
          .limit(1).get();

        if (!recentReport.empty) {
            return res.status(429).json({ error: 'بلغت عن هذا العنصر خلال 24 ساعة' });
        }

        // 2. إنشاء البلاغ
        const reportRef = db.collection('reports').doc();
        const report = {
            id: reportRef.id,
            reporterId: uid,
            targetType, // service, user, order, review
            targetId,
            reason, // spam, fraud, inappropriate, fake, other
            description: description || '',
            evidence: evidence || [], // روابط صور
            status: 'pending', // pending, reviewed, resolved, dismissed
            priority: calculatePriority(reason, uid), // high, medium, low
            createdAt: admin.firestore.FieldValue.serverTimestamp()
        };

        await reportRef.set(report);

        // 3. فحص تلقائي للغش
        const autoAction = await checkAutoModeration(targetType, targetId, reason);
        if (autoAction) {
            await db.collection('reports').doc(reportRef.id).update({
                status: 'resolved',
                autoResolved: true,
                action: autoAction
            });
        }

        // 4. إشعار للمشرف على التليجرام
        const targetData = await getTargetData(targetType, targetId);
        const msg = `🚨 <b>بلاغ جديد - ${report.priority.toUpperCase()}</b>\n\n` +
                    `النوع: ${targetType}\n` +
                    `السبب: ${reason}\n` +
                    `الهدف: ${targetData?.name || targetId}\n` +
                    `الوصف: ${description}\n\n` +
                    `/review_report_${reportRef.id}`;

        await notifyAdminTelegram(msg);

        // 5. إشعار للمبلغ
        await sendNotification({
            userId: uid,
            type: 'report',
            title: '✅ تم استلام بلاغك',
            body: autoAction ? 'تم اتخاذ إجراء تلقائي' : 'سيتم المراجعة خلال 24 ساعة',
            data: { reportId: reportRef.id }
        });

        await logAction(uid, 'create_report', 'report', reportRef.id, { targetType, reason }, 'success');
        res.json({ success: true, reportId: reportRef.id, autoResolved: !!autoAction });

    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

function calculatePriority(reason, uid) {
    const highPriority = ['fraud', 'scam', 'illegal'];
    const mediumPriority = ['inappropriate', 'fake', 'spam'];

    if (highPriority.includes(reason)) return 'high';
    if (mediumPriority.includes(reason)) return 'medium';
    return 'low';
}

// فحص تلقائي للغش
async function checkAutoModeration(targetType, targetId, reason) {
    // 1. إذا وصل 3 بلاغات على نفس الخدمة خلال ساعة = إخفاء مؤقت
    if (targetType === 'service') {
        const recentReports = await db.collection('reports')
          .where('targetId', '==', targetId)
          .where('createdAt', '>', new Date(Date.now() - 60 * 60 * 1000))
          .get();

        if (recentReports.size >= 3) {
            await db.collection('services').doc(targetId).update({
                status: 'hidden',
                hiddenReason: 'auto_moderation',
                hiddenAt: admin.firestore.FieldValue.serverTimestamp()
            });
            return 'service_hidden';
        }
    }

    // 2. إذا المستخدم عنده 5 بلاغات مقبولة = تجميد محفظة
    if (targetType === 'user') {
        const userReports = await db.collection('reports')
          .where('targetId', '==', targetId)
          .where('status', '==', 'resolved')
          .get();

        if (userReports.size >= 5) {
            await db.collection('users').doc(targetId).update({
                walletFrozen: true,
                frozenReason: 'multiple_reports'
            });
            return 'wallet_frozen';
        }
    }

    return null;
}

async function getTargetData(type, id) {
    try {
        const doc = await db.collection(type + 's').doc(id).get();
        return doc.data();
    } catch {
        return null;
    }
}

// ======================== 22. نظام الحظر التلقائي ========================
app.post('/api/admin/auto-ban-check', async (req, res) => {
    try {
        const { uid } = req.body;

        // قواعد الحظر التلقائي
        const checks = await Promise.all([
            checkSpamCreation(uid),      // إنشاء 10 خدمات في ساعة
            checkFakeOrders(uid),        // 5 طلبات ملغية متتالية
            checkPointsAbuse(uid),       // تحويل نقاط مشبوه
            checkMultipleAccounts(uid)   // أكثر من 3 حسابات من نفس الجهاز
        ]);

        const violations = checks.filter(c => c.violated);

        if (violations.length > 0) {
            // تجميد فوري
            await db.collection('users').doc(uid).update({
                walletFrozen: true,
                banned: true,
                banReason: 'auto_ban',
                violations: violations.map(v => v.type),
                bannedAt: admin.firestore.FieldValue.serverTimestamp()
            });

            // إشعار للمشرف
            await notifyAdminTelegram(`🔴 <b>حظر تلقائي</b>\n\n` +
                `المستخدم: ${uid}\n` +
                `المخالفات: ${violations.map(v => v.type).join(', ')}\n\n` +
                `/unban_${uid} - فك الحظر`);

            await logAction('system', 'auto_ban', 'user', uid, { violations }, 'success');
            return res.json({ banned: true, violations });
        }

        res.json({ banned: false });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

async function checkSpamCreation(uid) {
    const hourAgo = new Date(Date.now() - 60 * 60 * 1000);
    const services = await db.collection('services')
      .where('userId', '==', uid)
      .where('createdAt', '>', hourAgo)
      .get();

    return {
        violated: services.size >= 10,
        type: 'spam_creation',
        count: services.size
    };
}

async function checkFakeOrders(uid) {
    const orders = await db.collection('orders')
      .where('buyerId', '==', uid)
      .orderBy('createdAt', 'desc')
      .limit(5)
      .get();

    const cancelled = orders.docs.filter(d => d.data().status === 'cancelled').length;
    return {
        violated: cancelled >= 5,
        type: 'fake_orders',
        count: cancelled
    };
}

async function checkPointsAbuse(uid) {
    const hourAgo = new Date(Date.now() - 60 * 60 * 1000);
    const tx = await db.collection('wallet_transactions')
      .where('userId', '==', uid)
      .where('type', '==', 'spend')
      .where('createdAt', '>', hourAgo)
      .get();

    const totalSpent = tx.docs.reduce((sum, d) => sum + Math.abs(d.data().amount), 0);
    return {
        violated: totalSpent > 10000, // أكثر من 10K نقطة في ساعة
        type: 'points_abuse',
        amount: totalSpent
    };
}

async function checkMultipleAccounts(uid) {
    const userDoc = await db.collection('users').doc(uid).get();
    const deviceId = userDoc.data()?.deviceId;
    if (!deviceId) return { violated: false, type: 'multiple_accounts' };

    const sameDevice = await db.collection('users')
      .where('deviceId', '==', deviceId)
      .get();

    return {
        violated: sameDevice.size > 3,
        type: 'multiple_accounts',
        count: sameDevice.size
    };
}

// ======================== 23. التقارير المالية للمشرف ========================
app.get('/api/admin/financial-report', async (req, res) => {
    try {
        const { adminUid, startDate, endDate } = req.query;

        const adminDoc = await db.collection('users').doc(adminUid).get();
        if (adminDoc.data().role !== 'admin') return res.status(403).json({ error: 'غير مصرح' });

        const start = new Date(startDate);
        const end = new Date(endDate);

        const [transactions, orders, services] = await Promise.all([
            db.collection('wallet_transactions')
              .where('createdAt', '>=', start)
              .where('createdAt', '<=', end)
              .get(),
            db.collection('orders')
              .where('createdAt', '>=', start)
              .where('createdAt', '<=', end)
              .get(),
            db.collection('services')
              .where('createdAt', '>=', start)
              .where('createdAt', '<=', end)
              .get()
        ]);

        // حساب الإحصائيات
        let totalPointsEarned = 0;
        let totalPointsSpent = 0;
        let totalPointsRefunded = 0;

        transactions.docs.forEach(doc => {
            const tx = doc.data();
            if (tx.type === 'earn' || tx.type === 'bonus') totalPointsEarned += tx.amount;
            if (tx.type === 'spend') totalPointsSpent += Math.abs(tx.amount);
            if (tx.type === 'refund') totalPointsRefunded += tx.amount;
        });

        const totalOrders = orders.size;
        const completedOrders = orders.docs.filter(d => d.data().status === 'completed').length;
        const totalRevenue = orders.docs
          .filter(d => d.data().status === 'completed')
          .reduce((sum, d) => sum + d.data().servicePrice, 0);

        const conversionRate = totalOrders > 0 ? (completedOrders / totalOrders * 100).toFixed(2) : 0;

        // أفضل البائعين
        const sellerStats = {};
        orders.docs.forEach(doc => {
            const o = doc.data();
            if (o.status === 'completed') {
                if (!sellerStats[o.sellerId]) sellerStats[o.sellerId] = { revenue: 0, orders: 0 };
                sellerStats[o.sellerId].revenue += o.servicePrice;
                sellerStats[o.sellerId].orders += 1;
            }
        });

        const topSellers = await Promise.all(
            Object.entries(sellerStats)
              .sort((a, b) => b[1].revenue - a[1].revenue)
              .slice(0, 10)
              .map(async ([sellerId, stats]) => {
                  const userDoc = await db.collection('users').doc(sellerId).get();
                  return {
                      sellerId,
                      name: userDoc.data()?.name || 'مستخدم',
                      ...stats
                  };
              })
        );

        res.json({
            success: true,
            period: { start: startDate, end: endDate },
            points: {
                earned: totalPointsEarned,
                spent: totalPointsSpent,
                refunded: totalPointsRefunded,
                circulation: totalPointsEarned - totalPointsSpent + totalPointsRefunded
            },
            orders: {
                total: totalOrders,
                completed: completedOrders,
                conversionRate: parseFloat(conversionRate),
                totalRevenue: parseFloat(totalRevenue.toFixed(2))
            },
            services: {
                created: services.size
            },
            topSellers
        });
    } catch (error) {
        res.status(500).json({ error: error.message });
    }
});

